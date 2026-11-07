"""
Thai (`U+0E00..U+0E7F`) and Lao (`U+0E80..U+0EFF`) script support for `pyvim`.

Adapts the cell-cluster and differential renderer architecture from `szn`
(`src/thai.zig`, `src/mode_copy.zig`, `src/server/render.zig`):

1. Character-wise Vi motions and edits (`h`, `l`, `j`, `k`, `x`, `X`, `s`,
   `r`, `~`, `$`, `a`, `<Esc>`) step by terminal cell clusters (`base + comb*`)
   so the cursor never parks on a zero-width combining mark (`GC=Mn`) and edits
   never slice a cluster in half.
2. Word-wise Vi motions and text objects (`w`, `b`, `e`, `W`, `B`, `E`, `iw`,
   `aw`, `*`, `#`) segment unspaced Thai/Lao text using a two-tier strategy:
   Tier 1 (`libthai` dictionary breaker via `ctypes`, optional at runtime) with
   Tier 2 (`find_thai_cluster_end` orthographic syllable cluster heuristic) as
   an always-available fallback.
3. Differential terminal rendering (`prompt_toolkit.renderer._output_screen_diff`)
   cleans up stray zero-width combining marks and invalidates the neighbor cell
   whenever Thai/Lao `SARA AM` (`U+0E33` / `U+0EB3`) or its preceding consonant
   at `x - 1` changes.
"""

from __future__ import annotations

import asyncio
import ctypes
import inspect
import logging
import re
import threading
import unicodedata
from functools import lru_cache
from typing import Any, Callable, Pattern

import prompt_toolkit.renderer as ptk_renderer
from prompt_toolkit.document import Document
from prompt_toolkit.filters.app import vi_navigation_mode
from prompt_toolkit.key_binding.key_processor import KeyPressEvent, KeyProcessor
from prompt_toolkit.layout.screen import Char, Screen
from prompt_toolkit.utils import get_cwidth

__all__ = (
    "is_thai",
    "is_lao",
    "is_thai_or_lao",
    "is_thai_combining",
    "is_combining_char",
    "is_sara_am",
    "is_thai_leading_vowel",
    "is_thai_following_vowel",
    "is_thai_right_attaching",
    "is_thai_base",
    "snap_to_cell_start",
    "next_cell_offset",
    "prev_cell_offset",
    "cell_starts",
    "cell_stops",
    "find_thai_cluster_end",
    "find_thai_word_breaks",
    "find_next_word_beginning",
    "find_next_word_ending",
    "find_previous_word_beginning",
    "find_previous_word_ending",
    "find_start_of_previous_word",
    "find_boundaries_of_current_word",
    "get_word_under_cursor",
    "install_prompt_toolkit_thai_patches",
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Thai & Lao Character Classification Predicates
# ---------------------------------------------------------------------------

# Complete 34-codepoint set of Thai (16) and Lao (18) GC=Mn combining marks,
# matching `szn/src/thai.zig:28-70` (`isThaiCombining`) 1-for-1.
# Note: SARA AM (U+0E33 / U+0EB3) is GC=Lo (spacing following vowel, width 1), NOT Mn.
_THAI_COMBINING_CPS: frozenset[int] = frozenset(
    {
        # Thai combining marks (16 marks: U+0E31, U+0E34..U+0E3A, U+0E47..U+0E4E)
        0x0E31,  # MAI HAN-AKAT
        0x0E34,
        0x0E35,
        0x0E36,
        0x0E37,  # SARA I, II, UE, UEE
        0x0E38,
        0x0E39,
        0x0E3A,  # SARA U, UU, PHINTHU
        0x0E47,  # MAITAIKHU
        0x0E48,
        0x0E49,
        0x0E4A,
        0x0E4B,  # MAI EK, THO, TRI, CHATTAWA
        0x0E4C,
        0x0E4D,
        0x0E4E,  # THANTHAKHAT, NIKHAHIT, YAMAKKAN
        # Lao combining marks (18 marks: U+0EB1, U+0EB4..U+0EBC, U+0EC7..U+0ECE)
        0x0EB1,  # MAI KAN
        0x0EB4,
        0x0EB5,
        0x0EB6,
        0x0EB7,  # SARA I, II, Y, YY
        0x0EB8,
        0x0EB9,
        0x0EBA,
        0x0EBB,
        0x0EBC,  # SARA U, UU, PALI VIRAMA, MAI KON, LO
        0x0EC7,  # MAITAIKHU
        0x0EC8,
        0x0EC9,
        0x0ECA,
        0x0ECB,  # MAI EK, THO, TI, CATAWA
        0x0ECC,
        0x0ECD,
        0x0ECE,  # CANCELLATION MARK, NIKHAHIT, YAMAKKAN
    }
)

_FOLLOWING_VOWEL_CPS: frozenset[int] = frozenset(
    {
        0x0E30,
        0x0E31,
        0x0E32,
        0x0E33,
        0x0E45,  # Thai: ะ, ◌ั, า, ำ, ๅ
        0x0EB0,
        0x0EB1,
        0x0EB2,
        0x0EB3,  # Lao:  ະ, ◌ັ, າ, ຳ
    }
)

_RIGHT_ATTACHING_CPS: frozenset[int] = frozenset(
    {
        0x0E2F,
        0x0E46,  # Thai: ฯ (PAIYANNOI), ๆ (MAI YAMOK)
        0x0EAF,
        0x0EC6,  # Lao:  ຯ (ELLIPSIS),  ໆ (KO LA)
    }
)


def is_thai(cp: int) -> bool:
    """True if `cp` is in the Thai block (`U+0E00..U+0E7F`)."""
    return 0x0E00 <= cp <= 0x0E7F


def is_lao(cp: int) -> bool:
    """True if `cp` is in the Lao block (`U+0E80..U+0EFF`)."""
    return 0x0E80 <= cp <= 0x0EFF


def is_thai_or_lao(cp: int) -> bool:
    """True if `cp` is in the Thai (`U+0E00..U+0E7F`) or Lao (`U+0E80..U+0EFF`) blocks."""
    return 0x0E00 <= cp <= 0x0EFF


def is_thai_combining(cp: int) -> bool:
    """True if `cp` is one of the 34 Thai/Lao zero-width combining marks (`GC=Mn`)."""
    return cp in _THAI_COMBINING_CPS


def is_combining_char(ch: str) -> bool:
    """
    Fast-path check for Thai/Lao combining marks (`_THAI_COMBINING_CPS`),
    with general Unicode `Mn` / `get_cwidth(ch) == 0` fallback for other scripts.

    NOTE: characters below U+0300 always classify as non-combining — in
    particular `\n`. The cell-cluster scanners (`snap_to_cell_start`,
    `prev_cell_offset`) rely on newline never behaving like a combining
    mark so that backward walks over multi-line `Document.text` stop at
    line boundaries; keep that ordering when generalizing this predicate
    (see tests/test_thai.py::test_prev_cell_offset_never_crosses_newline
    and docs/bugs/014.md of the findings bundle).
    """
    if not ch:
        return False
    cp = ord(ch[0])
    if 0x0E00 <= cp <= 0x0EFF:
        return cp in _THAI_COMBINING_CPS
    if cp < 0x0300:
        return False
    return unicodedata.category(ch[0]) == "Mn" or get_cwidth(ch[0]) == 0


def is_sara_am(cp: int) -> bool:
    """True if `cp` is Thai SARA AM (`U+0E33`) or Lao SARA AM (`U+0EB3`)."""
    return cp == 0x0E33 or cp == 0x0EB3


def is_thai_leading_vowel(cp: int) -> bool:
    """True if `cp` is a visual-order leading vowel (`U+0E40..U+0E44`, `U+0EC0..U+0EC4`)."""
    return (0x0E40 <= cp <= 0x0E44) or (0x0EC0 <= cp <= 0x0EC4)


def is_thai_following_vowel(cp: int) -> bool:
    """True if `cp` is a Thai/Lao following vowel (`ะ`, `◌ั`, `า`, `ำ`, `ๅ` / `ະ`, `◌ັ`, `າ`, `ຳ`)."""
    return cp in _FOLLOWING_VOWEL_CPS


def is_thai_right_attaching(cp: int) -> bool:
    """True if `cp` is a right-attaching symbol (`ฯ` `U+0E2F`, `ๆ` `U+0E46`, `ຯ` `U+0EAF`, `ໆ` `U+0EC6`)."""
    return cp in _RIGHT_ATTACHING_CPS


_THAI_DIGIT_CPS = set(range(0x0E50, 0x0E5A)) | set(range(0x0ED0, 0x0EDA))
_THAI_SYMBOL_CPS = {0x0E3F, 0x0E4F, 0x0E5A, 0x0E5B}


def is_thai_base(cp: int) -> bool:
    """
    Port of `szn/src/thai.zig:126-133` (`isThaiBase`):
    True if `cp` is a width-1 Thai/Lao codepoint that is not a combining mark,
    leading vowel, following vowel, or right-attaching mark.
    """
    return (
        is_thai_or_lao(cp)
        and not is_thai_combining(cp)
        and not is_thai_leading_vowel(cp)
        and not is_thai_following_vowel(cp)
        and not is_thai_right_attaching(cp)
        and cp not in _THAI_DIGIT_CPS
        and cp not in _THAI_SYMBOL_CPS
        and get_cwidth(chr(cp)) == 1
    )


# ---------------------------------------------------------------------------
# 2. O(1) Local Cell-Cluster Boundary Scanners
# ---------------------------------------------------------------------------


def snap_to_cell_start(line: str, col: int) -> int:
    """
    If `col` is parked on a combining mark inside `line` (e.g. after vertical
    `j`/`k` motion), walk backward to the base character of the enclosing cell
    cluster.
    """
    n = len(line)
    if col <= 0 or n == 0 or line.isascii():
        return max(0, min(col, n))
    idx = min(col, n)
    while idx > 0 and idx < n and is_combining_char(line[idx]):
        idx -= 1
    return idx


def next_cell_offset(line: str, col: int, count: int = 1) -> int:
    """
    Advance `count` visual cell clusters forward from `col` within `line`.
    Returns the new column index in `0..len(line)`.
    """
    n = len(line)
    if col >= n or count <= 0:
        return n if col >= n else max(0, col)
    if line.isascii():
        return min(n, col + count)

    idx = max(0, col)
    for _ in range(count):
        if idx >= n:
            break
        idx += 1
        while idx < n and is_combining_char(line[idx]):
            idx += 1
    return idx


def prev_cell_offset(line: str, col: int, count: int = 1) -> int:
    """
    Move `count` visual cell clusters backward from `col` within `line`.
    Returns the new column index in `0..len(line)`.
    """
    if col <= 0 or count <= 0:
        return 0 if col <= 0 else min(col, len(line))
    if line.isascii():
        return max(0, col - count)

    idx = min(col, len(line))
    for _ in range(count):
        if idx <= 0:
            break
        idx -= 1
        while idx > 0 and is_combining_char(line[idx]):
            idx -= 1
    return idx


def cell_stops(line: str) -> list[int]:
    """
    Return all cell-cluster boundary offsets in `line`, including `len(line)`
    at the end (e.g. `"ที่ดิน"` -> `[0, 3, 5, 6]`).
    """
    stops = [0]
    col = 0
    n = len(line)
    while col < n:
        col = next_cell_offset(line, col, 1)
        stops.append(col)
    return stops


def cell_starts(line: str) -> list[int]:
    """
    Return valid Normal-mode cell start offsets in `line`
    (e.g. `"ที่ดิน"` -> `[0, 3, 5]`).
    """
    if not line:
        return []
    return cell_stops(line)[:-1]


# ---------------------------------------------------------------------------
# 3. Two-Tier Syllable & Word Segmentation (libthai + TCC-lite heuristic)
# ---------------------------------------------------------------------------

_LIBTHAI_PATHS: tuple[str, ...] = (
    "/opt/homebrew/lib/libthai.dylib",
    "/usr/local/lib/libthai.dylib",
    "/usr/lib/libthai.dylib",
    "/usr/local/lib64/libthai.so.0",
    "/usr/local/lib64/libthai.so",
    "/usr/lib64/libthai.so.0",
    "/usr/lib64/libthai.so",
    "/usr/lib/libthai.so.0",
    "/usr/lib/libthai.so",
    "/usr/lib/x86_64-linux-gnu/libthai.so.0",
    "/usr/lib/x86_64-linux-gnu/libthai.so",
    "/usr/lib/aarch64-linux-gnu/libthai.so.0",
    "/usr/lib/aarch64-linux-gnu/libthai.so",
    "libthai.so.0",
    "libthai.so",
    "libthai.dylib",
)


class _LibThaiWrapper:
    """
    Thread-safe wrapper around `libthai`'s wide-character word breaker
    (`th_brk_new`, `th_brk_wc_find_breaks`, `th_brk_delete`), ported from
    `szn/src/thai.zig:693-868`.
    """

    def __init__(self, lib: ctypes.CDLL, brk: int) -> None:
        self._lib = lib
        self._brk = ctypes.c_void_p(brk)
        self._call_lock = threading.Lock()

    def find_breaks(self, text: str) -> list[int]:
        n = len(text)
        if n <= 1:
            return []
        codepoints = (ctypes.c_uint32 * (n + 1))(*(ord(ch) for ch in text), 0)
        pos_buf = (ctypes.c_int * n)()
        with self._call_lock:
            num_breaks = int(self._lib.th_brk_wc_find_breaks(self._brk, codepoints, pos_buf, n))
        if num_breaks <= 0:
            return []

        result: list[int] = []
        for i in range(num_breaks):
            raw = int(pos_buf[i])
            if 0 < raw < n:
                snapped = snap_to_cell_start(text, raw)
                if 0 < snapped < n and (not result or result[-1] != snapped):
                    result.append(snapped)
        return result


_libthai_lock = threading.Lock()
_libthai_initialized = False
_libthai_instance: _LibThaiWrapper | None = None


def _get_libthai() -> _LibThaiWrapper | None:
    """Lazily initialize and return the singleton `_LibThaiWrapper`, or `None`."""
    global _libthai_initialized, _libthai_instance
    if _libthai_initialized:
        return _libthai_instance

    with _libthai_lock:
        if _libthai_initialized:
            return _libthai_instance

        for path in _LIBTHAI_PATHS:
            try:
                lib = ctypes.CDLL(path)
                th_brk_new = lib.th_brk_new
                th_brk_new.argtypes = [ctypes.c_char_p]
                th_brk_new.restype = ctypes.c_void_p

                th_brk_delete = lib.th_brk_delete
                th_brk_delete.argtypes = [ctypes.c_void_p]
                th_brk_delete.restype = None

                th_brk_wc_find_breaks = lib.th_brk_wc_find_breaks
                th_brk_wc_find_breaks.argtypes = [
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_uint32),
                    ctypes.POINTER(ctypes.c_int),
                    ctypes.c_size_t,
                ]
                th_brk_wc_find_breaks.restype = ctypes.c_int

                brk = th_brk_new(None)
                if not brk:
                    continue

                _libthai_instance = _LibThaiWrapper(lib, int(brk))
                break
            except (OSError, AttributeError):
                continue

        _libthai_initialized = True
        return _libthai_instance


def find_thai_cluster_end(line: str, start: int) -> int:
    """
    Codepoint-indexed port of `szn/src/thai.zig:285-326` (`findThaiClusterEnd`).
    Each cell is `[base_cp + combining*]` advanced via `next_cell_offset(line, pos, 1)`:
      `[leading_vowel] + base (+ optional Ro Han รร) + [following_vowel*] + [right_attaching*]`
    """
    n = len(line)
    if start >= n:
        return start
    cp = ord(line[start])
    if not is_thai_or_lao(cp):
        return next_cell_offset(line, start, 1)

    first_cell_end = next_cell_offset(line, start, 1)
    pos = start

    if is_thai_leading_vowel(cp):
        pos = first_cell_end
        if pos >= n:
            return first_cell_end

    base_cp = ord(line[pos])
    if not is_thai_base(base_cp):
        return first_cell_end

    # Check for Thai Ro Han (รร, U+0E23 + U+0E23) following the base consonant.
    after_base = next_cell_offset(line, pos, 1)
    r1_end = next_cell_offset(line, after_base, 1) if after_base < n else n
    if (
        after_base < n
        and r1_end < n
        and ord(line[after_base]) == 0x0E23
        and ord(line[r1_end]) == 0x0E23
    ):
        pos = next_cell_offset(line, r1_end, 1)
    else:
        pos = after_base

    while pos < n and is_thai_following_vowel(ord(line[pos])):
        pos = next_cell_offset(line, pos, 1)

    while pos < n and is_thai_right_attaching(ord(line[pos])):
        pos = next_cell_offset(line, pos, 1)

    return pos


def _cluster_breaks_for_span(text: str, start: int, end: int) -> list[int]:
    """Step through `text[start:end]` using Tier 2 `find_thai_cluster_end`."""
    breaks: list[int] = []
    pos = start
    while pos < end:
        next_pos = find_thai_cluster_end(text, pos)
        if next_pos <= pos or next_pos > end:
            next_pos = min(end, next_cell_offset(text, pos, 1))
        pos = next_pos
        breaks.append(pos)
    return breaks


def find_thai_word_breaks(text: str, use_libthai: bool = True) -> list[int]:
    """
    Return the sorted boundary offsets `[0, ..., len(text)]` segmenting `text`
    into Thai dictionary words (Tier 1: `libthai`) or orthographic syllable
    clusters (Tier 2 fallback: `find_thai_cluster_end`).
    """
    n = len(text)
    if n == 0:
        return [0]

    libthai = _get_libthai() if use_libthai else None
    if libthai is not None:
        all_thai = True
        has_thai_base = False
        for ch in text:
            cp = ord(ch)
            if not is_thai(cp):
                all_thai = False
                break
            if not has_thai_base and is_thai_base(cp):
                has_thai_base = True
        if all_thai and has_thai_base:
            internal = libthai.find_breaks(text)
            return [0, *internal, n]

    return [0, *_cluster_breaks_for_span(text, 0, n)]


_WORD_CHUNK_RE = re.compile(r"([\u0e00-\u0eff]+|[a-zA-Z0-9_]+|[^a-zA-Z0-9_\s\u0e00-\u0eff]+)")
_BIG_WORD_CHUNK_RE = re.compile(r"([\u0e00-\u0eff]+|[^\s\u0e00-\u0eff]+)")


def _word_spans_for_line(line: str, WORD: bool = False) -> tuple[tuple[int, int], ...]:
    """
    Partition a single line into ``(start, end)`` word spans, splitting Thai
    and Lao runs via `find_thai_word_breaks`.

    Cached per line (keyed on the line text and ``WORD``): word-level Vi
    motions and text objects re-scan only the lines they actually touch
    instead of the whole document on every keypress (see ``docs/bugs/001.md``).
    """
    regex = _BIG_WORD_CHUNK_RE if WORD else _WORD_CHUNK_RE
    spans: list[tuple[int, int]] = []
    for match in regex.finditer(line):
        m_start = match.start(0)
        m_end = match.end(0)
        chunk = match.group(0)
        if chunk and is_thai_or_lao(ord(chunk[0])):
            breaks = find_thai_word_breaks(chunk)
            for i in range(len(breaks) - 1):
                b0 = m_start + breaks[i]
                b1 = m_start + breaks[i + 1]
                if b0 < b1:
                    spans.append((b0, b1))
        else:
            spans.append((m_start, m_end))
    return tuple(spans)


# The span cache itself: word motions are pure functions of the (unchanged)
# line, so an LRU cache gives O(1) re-scans for repeat presses on the same
# text while using only line-sized keys.
_word_spans_for_line = lru_cache(maxsize=2048)(_word_spans_for_line)


def _iter_word_spans(text: str, WORD: bool = False) -> list[tuple[int, int]]:
    """
    Full-document word spans as absolute ``(start, end)`` offsets.

    Composed from the cached per-line spans and kept as the reference
    implementation (used by the test suite to pin equivalence of the
    line-local motion walkers against the whole-text scan).
    """
    spans: list[tuple[int, int]] = []
    offset = 0
    for line in text.split("\n"):
        for start, end in _word_spans_for_line(line, WORD):
            spans.append((offset + start, offset + end))
        offset += len(line) + 1
    return spans


def find_next_word_beginning(doc: Document, count: int = 1, WORD: bool = False) -> int | None:
    """
    Thai/Lao-aware replacement for `Document.find_next_word_beginning`.
    Returns an offset relative to `doc.cursor_position`, or `None`.
    """
    if count < 0:
        return find_previous_word_beginning(doc, count=-count, WORD=WORD)
    if doc.text.isascii():
        orig = _ORIGINAL_DOCUMENT_METHODS.get("find_next_word_beginning")
        if orig is not None:
            return orig(doc, count=count, WORD=WORD)

    pos = doc.cursor_position
    row = doc.cursor_position_row
    lines = doc.lines

    # Only spans starting strictly after the cursor qualify; walk the cursor
    # line first, then forward one line at a time (per-line span cache).
    line_start = doc.translate_row_col_to_index(row, 0)
    matched = 0
    for start, _end in _word_spans_for_line(lines[row], WORD):
        if line_start + start > pos:
            matched += 1
            if matched == count:
                return line_start + start - pos
    for row in range(row + 1, len(lines)):
        line_start = doc.translate_row_col_to_index(row, 0)
        for start, _end in _word_spans_for_line(lines[row], WORD):
            matched += 1
            if matched == count:
                return line_start + start - pos
    return None


def find_next_word_ending(
    doc: Document,
    include_current_position: bool = False,
    count: int = 1,
    WORD: bool = False,
) -> int | None:
    """
    Thai/Lao-aware replacement for `Document.find_next_word_ending`.
    Returns an exclusive end offset relative to `doc.cursor_position`, or `None`.
    """
    if count < 0:
        return find_previous_word_ending(doc, count=-count, WORD=WORD)
    if doc.text.isascii():
        orig = _ORIGINAL_DOCUMENT_METHODS.get("find_next_word_ending")
        if orig is not None:
            return orig(
                doc,
                include_current_position=include_current_position,
                count=count,
                WORD=WORD,
            )

    pos = doc.cursor_position
    row = doc.cursor_position_row
    lines = doc.lines

    # A span qualifies when its last cell cluster starts after the cursor
    # (the Vi `e` text object then subtracts one to rest on that cluster).
    line_start = doc.translate_row_col_to_index(row, 0)
    line = lines[row]
    matched = 0
    for _start, end in _word_spans_for_line(line, WORD):
        last_cell = line_start + prev_cell_offset(line, end, 1)
        if include_current_position:
            qualifies = line_start + end > pos
        else:
            qualifies = last_cell > pos
        if qualifies:
            matched += 1
            if matched == count:
                return line_start + end - pos
    for row in range(row + 1, len(lines)):
        line_start = doc.translate_row_col_to_index(row, 0)
        for _start, end in _word_spans_for_line(lines[row], WORD):
            matched += 1
            if matched == count:
                return line_start + end - pos
    return None


def find_previous_word_beginning(doc: Document, count: int = 1, WORD: bool = False) -> int | None:
    """
    Thai/Lao-aware replacement for `Document.find_previous_word_beginning`.
    Returns an offset relative to `doc.cursor_position`, or `None`.
    """
    if count < 0:
        return find_next_word_beginning(doc, count=-count, WORD=WORD)
    if doc.text.isascii():
        orig = _ORIGINAL_DOCUMENT_METHODS.get("find_previous_word_beginning")
        if orig is not None:
            return orig(doc, count=count, WORD=WORD)

    pos = doc.cursor_position
    row = doc.cursor_position_row
    lines = doc.lines

    # Only spans starting strictly before the cursor qualify; walk the cursor
    # line first, then backward one line at a time.
    line_start = doc.translate_row_col_to_index(row, 0)
    matched = 0
    for start, _end in reversed(_word_spans_for_line(lines[row], WORD)):
        if line_start + start < pos:
            matched += 1
            if matched == count:
                return line_start + start - pos
    for row in range(row - 1, -1, -1):
        line_start = doc.translate_row_col_to_index(row, 0)
        for start, _end in reversed(_word_spans_for_line(lines[row], WORD)):
            matched += 1
            if matched == count:
                return line_start + start - pos
    return None


def find_start_of_previous_word(
    doc: Document,
    count: int = 1,
    WORD: bool = False,
    pattern: Pattern[str] | None = None,
) -> int | None:
    """
    Thai/Lao-aware replacement for `Document.find_start_of_previous_word`
    (used by Vi `b`/`B` and `get_word_before_cursor`).
    """
    if pattern is not None or doc.text.isascii():
        orig = _ORIGINAL_DOCUMENT_METHODS.get("find_start_of_previous_word")
        if orig is not None:
            return orig(doc, count=count, WORD=WORD, pattern=pattern)
    return find_previous_word_beginning(doc, count=count, WORD=WORD)


def find_previous_word_ending(doc: Document, count: int = 1, WORD: bool = False) -> int | None:
    """
    Thai/Lao-aware replacement for `Document.find_previous_word_ending`
    (used by Vi `ge`/`gE`).
    """
    if count < 0:
        return find_next_word_ending(doc, count=-count, WORD=WORD)
    if doc.text.isascii():
        orig = _ORIGINAL_DOCUMENT_METHODS.get("find_previous_word_ending")
        if orig is not None:
            return orig(doc, count=count, WORD=WORD)

    pos = doc.cursor_position
    row = doc.cursor_position_row
    lines = doc.lines

    # A span qualifies when its end is at or before the cursor.
    line_start = doc.translate_row_col_to_index(row, 0)
    matched = 0
    for _start, end in reversed(_word_spans_for_line(lines[row], WORD)):
        if line_start + end <= pos:
            matched += 1
            if matched == count:
                return line_start + end - pos
    for row in range(row - 1, -1, -1):
        line_start = doc.translate_row_col_to_index(row, 0)
        for _start, end in reversed(_word_spans_for_line(lines[row], WORD)):
            matched += 1
            if matched == count:
                return line_start + end - pos
    return None


def find_boundaries_of_current_word(
    doc: Document,
    WORD: bool = False,
    include_leading_whitespace: bool = False,
    include_trailing_whitespace: bool = False,
) -> tuple[int, int]:
    """
    Thai/Lao-aware replacement for `Document.find_boundaries_of_current_word`
    (used by `iw`, `aw`, `iW`, `aW`, `get_word_under_cursor`, `*`, `#`).
    """
    line = doc.current_line
    if line.isascii():
        orig = _ORIGINAL_DOCUMENT_METHODS.get("find_boundaries_of_current_word")
        if orig is not None:
            return orig(
                doc,
                WORD=WORD,
                include_leading_whitespace=include_leading_whitespace,
                include_trailing_whitespace=include_trailing_whitespace,
            )

    col = doc.cursor_position_col
    n = len(line)
    if col >= n or line[col].isspace():
        if not include_leading_whitespace and not include_trailing_whitespace:
            return (0, 0)
        w_start = col
        w_end = col
        if include_leading_whitespace:
            while w_start > 0 and line[w_start - 1].isspace():
                w_start -= 1
        if include_trailing_whitespace:
            while w_end < n and line[w_end].isspace():
                w_end += 1
        return (w_start - col, w_end - col)

    for w_start, w_end in _word_spans_for_line(line, WORD):
        if w_start <= col < w_end:
            if include_leading_whitespace:
                while w_start > 0 and line[w_start - 1].isspace():
                    w_start -= 1
            if include_trailing_whitespace:
                while w_end < n and line[w_end].isspace():
                    w_end += 1
            return (w_start - col, w_end - col)
    return (0, 0)


def get_word_under_cursor(doc: Document, WORD: bool = False) -> str:
    """Return the Thai/Lao or ASCII word currently under the cursor."""
    start, end = find_boundaries_of_current_word(doc, WORD=WORD)
    return doc.text[doc.cursor_position + start : doc.cursor_position + end]


# ---------------------------------------------------------------------------
# 4. Document Cell-Cluster Cursor Movement Wrappers (Phase 2)
# ---------------------------------------------------------------------------


def _doc_get_cursor_left_position(self: Document, count: int = 1) -> int:
    if count < 0:
        return self.get_cursor_right_position(-count)
    line = self.current_line
    col = self.cursor_position_col
    if line.isascii():
        return -min(col, count)
    return prev_cell_offset(line, col, count) - col


def _doc_get_cursor_right_position(self: Document, count: int = 1) -> int:
    if count < 0:
        return self.get_cursor_left_position(-count)
    line = self.current_line
    col = self.cursor_position_col
    if line.isascii():
        return min(count, len(line) - col)
    return next_cell_offset(line, col, count) - col


def _vertical_cursor_position(
    self: Document, target_row: int, preferred_column: int | None = None
) -> int:
    """
    Index delta for moving to `target_row`, snapping the column to the
    nearest cell-cluster start of the target line (shared by the up/down
    Document wrappers; docs/bugs/029.md).
    """
    column = self.cursor_position_col if preferred_column is None else preferred_column
    target_line = self.lines[target_row]
    target_col = snap_to_cell_start(target_line, min(column, len(target_line)))
    return self.translate_row_col_to_index(target_row, target_col) - self.cursor_position


def _doc_get_cursor_up_position(
    self: Document, count: int = 1, preferred_column: int | None = None
) -> int:
    assert count >= 1
    return _vertical_cursor_position(
        self, max(0, self.cursor_position_row - count), preferred_column
    )


def _doc_get_cursor_down_position(
    self: Document, count: int = 1, preferred_column: int | None = None
) -> int:
    assert count >= 1
    target_row = min(len(self.lines) - 1, self.cursor_position_row + count)
    return _vertical_cursor_position(self, target_row, preferred_column)


def _kp_fix_vi_cursor_position(self: KeyProcessor, event: KeyPressEvent) -> None:
    """
    Cell-cluster-aware replacement for `KeyProcessor._fix_vi_cursor_position`.
    In Vi navigation mode, ensures the cursor never rests past EOL or on a
    zero-width combining mark after a key handler runs.
    """
    app = event.app
    buff = app.current_buffer
    preferred_column = buff.preferred_column
    doc = buff.document
    line = doc.current_line

    if vi_navigation_mode() and len(line) > 0:
        col = doc.cursor_position_col
        if doc.is_cursor_at_the_end_of_line:
            target_col = prev_cell_offset(line, len(line), 1)
        else:
            target_col = snap_to_cell_start(line, col)
        if target_col != col:
            buff.cursor_position += target_col - col
            buff.preferred_column = preferred_column


def _make_kp_start_timeout_wrapper(
    orig_start_timeout: Callable[[KeyProcessor], None],
) -> Callable[[KeyProcessor], None]:
    def _kp_start_timeout(self: KeyProcessor) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # When called synchronously from unit tests without a running
            # event loop (Python 3.10+ behaviour, error since 3.14), skip
            # spawning the background timeout coroutine entirely.
            return
        orig_start_timeout(self)

    return _kp_start_timeout


# ---------------------------------------------------------------------------
# 5. Differential Renderer Patch for Stray Marks & SARA AM (Phase 4)
# ---------------------------------------------------------------------------

_SARA_AM_POISON = Char(char="\x00", style="__pyvim_sara_am_invalidate__")

# C-speed detection for strings that may land on screen; ASCII strings are
# free (`str.isascii()`), so the gate never needs to scan a screen grid to
# decide whether one is worth the SARA-AM neighbor refresh.
_HAS_THAI_RE = re.compile("[\u0e00-\u0eff]")


class _ThaiTextGate:
    """
    Sticky "this session may render Thai/Lao text" flag.

    `prompt_toolkit` exposes no cheap hook that says whether a rendered
    `Screen` still contains Thai cells; scanning the whole grid per frame
    costs ~1.3 ms on a 50x200 terminal with plain-ASCII content
    (``docs/bugs/002.md``). Instead, pyvim reports the strings that reach
    the screen (buffer text, buffer locations, command/search lines) via
    `note_document_text` and the renderer wrapper skips the neighbor scan
    entirely while the flag is still ``False``. Once latched ``True`` the
    flag stays on for the rest of the session, so sessions that ever showed
    Thai/Lao keep the full (correct) renderer behavior.
    """

    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = False

    def note(self, text: str | None) -> None:
        """Record a string that may be rendered (sticky-latch on Thai)."""
        if self.value or not text or text.isascii():
            return
        if _HAS_THAI_RE.search(text):
            self.value = True

    def reset(self) -> None:
        """Reset for tests; production sessions never call this."""
        self.value = False


_THAI_GATE = _ThaiTextGate()


def note_document_text(text: str | None) -> None:
    """
    Report a string that may be rendered on screen (buffer content, buffer
    location, command or search line) to the renderer gate.
    """
    _THAI_GATE.note(text)


def reset_thai_text_gate() -> None:
    """Reset the sticky renderer gate (used by the test suite)."""
    _THAI_GATE.reset()


def _cell_has_sara_am(cell: Char) -> bool:
    ch = cell.char
    if not ch:
        return False
    first = ord(ch[0])
    if first == 0x0E33 or first == 0x0EB3:
        return True
    return "\u0e33" in ch or "\u0eb3" in ch


def _sanitize_and_invalidate_sara_am(
    new_screen: Screen, previous_screen: Screen | None, width: int
) -> None:
    """
    1. Clear any stray zero-width combining mark cells (`cell.width == 0 and cell.char != ""`)
       left at the end of `FormattedTextControl` or wrapped lines.
    2. Port `szn` commit `71ba808` (`src/server/render.zig:664-694`): when Thai/Lao
       `SARA AM` (`U+0E33` / `U+0EB3`) at column `x` or its preceding cell `x - 1`
       changes, poison the neighbor in `previous_screen` so `_output_screen_diff`
       re-emits both cells together.
    """
    row_indices = set(new_screen.data_buffer.keys())
    if previous_screen is not None:
        row_indices.update(previous_screen.data_buffer.keys())

    for y in row_indices:
        new_row = new_screen.data_buffer[y]

        # 1. Clear stray width-0 combining cells not overwritten by a trailing
        #    character. (Only values are replaced, so mutating while
        #    iterating `items()` is safe and avoids copying the row.)
        for x, cell in new_row.items():
            if cell.width == 0 and cell.char != "":
                new_row[x] = Char(char=" ", style=cell.style)

        # 2. SARA AM neighbor invalidation for differential rendering.
        if previous_screen is None or y not in previous_screen.data_buffer:
            continue
        prev_row = previous_screen.data_buffer[y]
        row_max_x = (
            max(
                max(new_row.keys(), default=0),
                max(prev_row.keys(), default=0),
            )
            + 1
        )
        max_x = min(width, row_max_x)

        for x in range(1, max_x):
            prev_cell = prev_row[x]
            cur_cell = new_row[x]
            if _cell_has_sara_am(prev_cell) or _cell_has_sara_am(cur_cell):
                prev_left = prev_row[x - 1]
                cur_left = new_row[x - 1]
                left_changed = (cur_left.char != prev_left.char) or (
                    cur_left.style != prev_left.style
                )
                cur_changed = (cur_cell.char != prev_cell.char) or (
                    cur_cell.style != prev_cell.style
                )
                if cur_changed and not left_changed:
                    prev_row[x - 1] = _SARA_AM_POISON
                elif left_changed and not cur_changed:
                    prev_row[x] = _SARA_AM_POISON


def _install_renderer_patch() -> bool:
    """
    Wrap `prompt_toolkit.renderer._output_screen_diff` with signature verification.
    Returns `True` if installed (or already installed), `False` if skipped.
    """
    orig_diff = getattr(ptk_renderer, "_output_screen_diff", None)
    if orig_diff is None:
        logger.warning("prompt_toolkit.renderer._output_screen_diff not found; skipping patch.")
        return False
    if getattr(orig_diff, "_pyvim_thai_patched", False):
        return True

    try:
        params = list(inspect.signature(orig_diff).parameters.keys())
    except (TypeError, ValueError):
        logger.warning("Could not inspect _output_screen_diff signature; skipping patch.")
        return False

    if len(params) < 12 or params[2] != "screen" or params[5] != "previous_screen":
        logger.warning(
            "Unexpected _output_screen_diff parameters %r; skipping renderer patch.",
            params,
        )
        return False

    def _wrapped_output_screen_diff(*args, **kwargs):
        screen = args[2] if len(args) > 2 else kwargs.get("screen")
        previous_screen = args[5] if len(args) > 5 else kwargs.get("previous_screen")
        size = kwargs.get("size") or (args[11] if len(args) > 11 else None)
        # Skip the full-screen scan while the sticky gate says this session
        # has never rendered Thai/Lao text (see `docs/bugs/002.md`); once a
        # Thai-capable string was observed, always sanitize (unchanged
        # semantics).
        if _THAI_GATE.value and screen is not None:
            width = size.columns if size is not None else 80
            _sanitize_and_invalidate_sara_am(screen, previous_screen, width)
        return orig_diff(*args, **kwargs)

    setattr(_wrapped_output_screen_diff, "_pyvim_thai_patched", True)
    setattr(_wrapped_output_screen_diff, "_pyvim_original", orig_diff)
    ptk_renderer._output_screen_diff = _wrapped_output_screen_diff  # type: ignore[assignment]
    return True


# ---------------------------------------------------------------------------
# 6. Version-Gated prompt_toolkit Patch Installer (Section 4.1)
# ---------------------------------------------------------------------------

_ORIGINAL_DOCUMENT_METHODS: dict[str, Callable[..., Any]] = {}

# Originals for the KeyProcessor patches (mirrors `_ORIGINAL_DOCUMENT_METHODS`).
_ORIGINAL_KEY_PROCESSOR_METHODS: dict[str, Callable[..., Any]] = {}

_DOCUMENT_PATCH_SPECS: tuple[tuple[str, tuple[str, ...], Callable[..., object]], ...] = (
    ("get_cursor_left_position", ("self", "count"), _doc_get_cursor_left_position),
    ("get_cursor_right_position", ("self", "count"), _doc_get_cursor_right_position),
    (
        "get_cursor_up_position",
        ("self", "count", "preferred_column"),
        _doc_get_cursor_up_position,
    ),
    (
        "get_cursor_down_position",
        ("self", "count", "preferred_column"),
        _doc_get_cursor_down_position,
    ),
    ("find_next_word_beginning", ("self", "count", "WORD"), find_next_word_beginning),
    (
        "find_next_word_ending",
        ("self", "include_current_position", "count", "WORD"),
        find_next_word_ending,
    ),
    (
        "find_previous_word_beginning",
        ("self", "count", "WORD"),
        find_previous_word_beginning,
    ),
    (
        "find_previous_word_ending",
        ("self", "count", "WORD"),
        find_previous_word_ending,
    ),
    (
        "find_start_of_previous_word",
        ("self", "count", "WORD", "pattern"),
        find_start_of_previous_word,
    ),
    (
        "find_boundaries_of_current_word",
        ("self", "WORD", "include_leading_whitespace", "include_trailing_whitespace"),
        find_boundaries_of_current_word,
    ),
)


def install_prompt_toolkit_thai_patches() -> bool:
    """
    Install Thai/Lao cell-cluster and renderer patches onto `prompt_toolkit`
    with signature checks, startup self-test, and graceful fallback.
    """
    # Every patch applied in this call, so the except-path can roll back to
    # an entirely unpatched prompt_toolkit (docs/bugs/005.md): (target,
    # attribute, original function) triples.
    applied: list[tuple[type, str, object]] = []
    try:
        for method_name, expected_params, replacement in _DOCUMENT_PATCH_SPECS:
            current = getattr(Document, method_name, None)
            if current is None:
                raise RuntimeError(f"Document.{method_name} is missing")
            if getattr(current, "_pyvim_thai_patched", False):
                continue

            sig_params = tuple(inspect.signature(current).parameters.keys())
            if sig_params[: len(expected_params)] != expected_params:
                raise RuntimeError(
                    f"Document.{method_name} signature {sig_params!r} "
                    f"does not match expected {expected_params!r}"
                )

            _ORIGINAL_DOCUMENT_METHODS.setdefault(method_name, current)
            setattr(replacement, "_pyvim_thai_patched", True)
            setattr(Document, method_name, replacement)
            applied.append((Document, method_name, current))

        # Patch KeyProcessor._fix_vi_cursor_position and _start_timeout.
        kp_fix = getattr(KeyProcessor, "_fix_vi_cursor_position", None)
        if kp_fix is not None and not getattr(kp_fix, "_pyvim_thai_patched", False):
            kp_params = tuple(inspect.signature(kp_fix).parameters.keys())
            if kp_params[:2] == ("self", "event"):
                _ORIGINAL_KEY_PROCESSOR_METHODS.setdefault("_fix_vi_cursor_position", kp_fix)
                setattr(_kp_fix_vi_cursor_position, "_pyvim_thai_patched", True)
                setattr(KeyProcessor, "_fix_vi_cursor_position", _kp_fix_vi_cursor_position)
                applied.append((KeyProcessor, "_fix_vi_cursor_position", kp_fix))

        kp_timeout = getattr(KeyProcessor, "_start_timeout", None)
        if kp_timeout is not None and not getattr(kp_timeout, "_pyvim_thai_patched", False):
            _ORIGINAL_KEY_PROCESSOR_METHODS.setdefault("_start_timeout", kp_timeout)
            wrapped_timeout = _make_kp_start_timeout_wrapper(kp_timeout)
            setattr(wrapped_timeout, "_pyvim_thai_patched", True)
            setattr(KeyProcessor, "_start_timeout", wrapped_timeout)
            applied.append((KeyProcessor, "_start_timeout", kp_timeout))

        # Startup self-test required by Section 4.1:
        test_doc = Document("ที่ดิน", cursor_position=0)
        if test_doc.get_cursor_right_position(1) != 3:
            raise RuntimeError(
                "Thai Document self-test failed: "
                "Document('ที่ดิน', 0).get_cursor_right_position(1) != 3"
            )
    except Exception as exc:
        for target, attribute, orig_fn in applied:
            setattr(target, attribute, orig_fn)
        logger.warning("Falling back to unpatched prompt_toolkit Document: %s", exc)
        return False

    _install_renderer_patch()
    return True


# Install on import so `Document` methods are immediately Thai-aware.
install_prompt_toolkit_thai_patches()
