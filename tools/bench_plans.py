#!/usr/bin/env python3
# mypy: disable-error-code="import-not-found,import-untyped,misc"
"""
Reproducible verification & micro-benchmarks backing the OKF v0.2 plans in docs/:
  - docs/thai_support_plan.md
  - docs/speed_latency_plan.md

Run with:
    python tools/bench_plans.py
"""

from __future__ import annotations

import bisect
import importlib
import platform
import re
import time
import unicodedata
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from typing import Any

import prompt_toolkit
from prompt_toolkit.completion import CompleteEvent, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text.base import StyleAndTextTuples
from prompt_toolkit.formatted_text.utils import split_lines
from prompt_toolkit.lexers.base import Lexer, SimpleLexer
from prompt_toolkit.lexers.pygments import PygmentsLexer, RegexSync, SyntaxSync
from prompt_toolkit.styles.pygments import pygments_token_to_classname
from prompt_toolkit.utils import get_cwidth

# ---------------------------------------------------------------------------
# 1. Reference Thai & Lao cell-cluster / syllable helpers (docs/thai_support_plan.md)
# ---------------------------------------------------------------------------

# Complete 34-codepoint set of Thai (16) and Lao (18) GC=Mn combining marks,
# matching `szn/src/thai.zig:28-70` (`isThaiCombining`).
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
        # Lao combining marks (18 marks: U+0EB1, U+0EB4..0x0EBC, 0x0EC7..0x0ECE)
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


def is_thai_or_lao(cp: int) -> bool:
    return 0x0E00 <= cp <= 0x0EFF


def is_thai_combining(cp: int) -> bool:
    return cp in _THAI_COMBINING_CPS


def is_combining_char(ch: str) -> bool:
    cp = ord(ch)
    if 0x0E00 <= cp <= 0x0EFF:
        return cp in _THAI_COMBINING_CPS
    if cp < 0x0300:
        return False
    return unicodedata.category(ch) == "Mn" or get_cwidth(ch) == 0


def is_sara_am(cp: int) -> bool:
    return cp == 0x0E33 or cp == 0x0EB3


def is_thai_leading_vowel(cp: int) -> bool:
    return (0x0E40 <= cp <= 0x0E44) or (0x0EC0 <= cp <= 0x0EC4)


def is_thai_following_vowel(cp: int) -> bool:
    return cp in (
        0x0E30,
        0x0E31,
        0x0E32,
        0x0E33,
        0x0E45,
        0x0EB0,
        0x0EB1,
        0x0EB2,
        0x0EB3,
    )


def is_thai_right_attaching(cp: int) -> bool:
    return cp in (0x0E2F, 0x0E46, 0x0EAF, 0x0EC6)


def is_thai_base(cp: int) -> bool:
    return (
        is_thai_or_lao(cp)
        and not is_thai_combining(cp)
        and not is_thai_leading_vowel(cp)
        and not is_thai_following_vowel(cp)
        and not is_thai_right_attaching(cp)
        and get_cwidth(chr(cp)) == 1
    )


def next_cell_offset(line: str, col: int, count: int = 1) -> int:
    n = len(line)
    if col >= n or count <= 0:
        return n
    if line.isascii():
        return min(n, col + count)
    idx = col
    for _ in range(count):
        if idx >= n:
            break
        idx += 1
        while idx < n and is_combining_char(line[idx]):
            idx += 1
    return idx


def prev_cell_offset(line: str, col: int, count: int = 1) -> int:
    if col <= 0 or count <= 0:
        return 0
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


def find_thai_cluster_end(line: str, start: int) -> int:
    """
    Codepoint-indexed port of `szn/src/thai.zig:285-326` (`findThaiClusterEnd`).
    Each cell is `[base_cp + combining*]` advanced via `next_cell_offset(line, pos, 1)`:
      [leading_vowel] + base (+ optional Ro Han รร) + [following_vowel*] + [right_attaching*]
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

    # Advance past the base cell, checking for Thai Ro Han (รร, U+0E23 + U+0E23)
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


def cell_stops(line: str) -> list[int]:
    stops = [0]
    col = 0
    while col < len(line):
        col = next_cell_offset(line, col, 1)
        stops.append(col)
    return stops


# ---------------------------------------------------------------------------
# 2. Speed Plan prototypes (docs/speed_latency_plan.md)
# ---------------------------------------------------------------------------


class _DummyEditorBuffer:
    def __init__(self, location: str) -> None:
        self.location = location
        self.in_file_explorer_mode = False


_STYLE_TOKEN_CACHE: dict[Any, str] = {}


class _PublicStreamingDocumentLexer(Lexer):
    """
    Replacement for `DocumentLexer` in `pyvim/lexer.py` using ONLY public
    `pygments` and `prompt_toolkit` APIs (`get_lexer_for_filename`,
    `get_tokens_unprocessed`, `RegexSync`, `split_lines`,
    `pygments_token_to_classname`).

    Avoids `prompt_toolkit`'s eager `list(get_text_fragments())` (`pygments.py:264`)
    while keeping `get_tokens_unprocessed` as a single continuous generator from
    `start_lineno` so multiline strings/docstrings never reset mid-token.
    """

    MIN_LINES_BACKWARDS = 50
    REUSE_GENERATOR_MAX_DISTANCE = 100

    def __init__(self, editor_buffer: _DummyEditorBuffer) -> None:
        self.editor_buffer = editor_buffer
        self._cached_location: str | None = None
        self._pygments_lexer: Any = None
        self._syntax_sync: SyntaxSync | None = None

    def _ensure_lexer(self, location: str) -> bool:
        if self._cached_location == location and self._pygments_lexer is not None:
            return True
        from pygments.lexers import get_lexer_for_filename
        from pygments.util import ClassNotFound

        try:
            lexer_inst = get_lexer_for_filename(
                location, stripnl=False, stripall=False, ensurenl=False
            )
        except ClassNotFound:
            self._cached_location = location
            self._pygments_lexer = None
            self._syntax_sync = None
            return False

        self._cached_location = location
        self._pygments_lexer = lexer_inst
        self._syntax_sync = RegexSync.from_pygments_lexer_cls(lexer_inst.__class__)
        return True

    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        location = self.editor_buffer.location
        if not location or not self._ensure_lexer(location):
            fallback: Callable[[int], StyleAndTextTuples] = SimpleLexer().lex_document(document)
            return fallback

        pygments_lexer = self._pygments_lexer
        syntax_sync = self._syntax_sync
        assert syntax_sync is not None

        LineGenerator = Generator[tuple[int, StyleAndTextTuples], None, None]
        cache: dict[int, StyleAndTextTuples] = {}
        line_generators: dict[LineGenerator, int] = {}

        def create_line_generator(start_lineno: int, column: int = 0) -> LineGenerator:
            def get_text_fragments() -> Iterable[tuple[str, str]]:
                text = "\n".join(document.lines[start_lineno:])[column:]
                for _, t, v in pygments_lexer.get_tokens_unprocessed(text):
                    try:
                        style_cls = _STYLE_TOKEN_CACHE[t]
                    except KeyError:
                        style_cls = "class:" + pygments_token_to_classname(t)
                        _STYLE_TOKEN_CACHE[t] = style_cls
                    yield style_cls, v

            yield from enumerate(split_lines(get_text_fragments()), start_lineno)

        def find_closest_generator(i: int) -> LineGenerator | None:
            for generator, lineno in line_generators.items():
                if lineno < i and i - lineno < self.REUSE_GENERATOR_MAX_DISTANCE:
                    return generator
            return None

        def get_generator(i: int) -> LineGenerator:
            generator = find_closest_generator(i)
            if generator:
                return generator
            start = max(0, i - self.MIN_LINES_BACKWARDS)
            if start == 0:
                row, column = 0, 0
            else:
                row, column = syntax_sync.get_sync_start_position(document, start)
            generator = find_closest_generator(i)
            if not generator:
                generator = create_line_generator(row, column)
            if column:
                next(generator)
                row += 1
            line_generators[generator] = row
            return generator

        def get_line(i: int) -> StyleAndTextTuples:
            try:
                return cache[i]
            except KeyError:
                generator = get_generator(i)
                for num, line in generator:
                    cache[num] = line
                    if num == i:
                        line_generators[generator] = i
                        if num + 1 in cache:
                            del cache[num + 1]
                        return cache[num]
            return []

        return get_line


class _LazyStylesDict(Mapping[str, Any]):
    """
    Lazy mapping for `editor.styles` (`pyvim/style.py`).
    Defers `pygments.styles.get_all_styles()` (which scans `importlib.metadata`
    entry points) until `:colorscheme <Tab>` actually iterates `editor.styles`.
    """

    def __init__(self, loader: Callable[[str], Any]) -> None:
        self._loader = loader
        self._names: list[str] | None = None
        self._loaded: dict[str, Any] = {}

    def _ensure_names(self) -> list[str]:
        if self._names is None:
            from pygments.styles import get_all_styles

            self._names = list(get_all_styles())
        return self._names

    def __iter__(self) -> Iterator[str]:
        return iter(self._ensure_names())

    def __len__(self) -> int:
        return len(self._ensure_names())

    def __getitem__(self, name: str) -> Any:
        if name not in self._loaded:
            self._loaded[name] = self._loader(name)
        return self._loaded[name]


class _SingletonCachedWordsCompleter:
    _WORD_RE = re.compile(r"\w+")

    def __init__(self) -> None:
        self._cached_key: tuple[int, int, str, str] | None = None
        self._other_words_sorted: list[str] = []

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        word_before_cursor = document.get_word_before_cursor()
        if not word_before_cursor:
            return
        row = document.cursor_position_row
        doc_lines = document.lines
        line_start = document.translate_row_col_to_index(row, 0)
        line_end = line_start + len(doc_lines[row])
        prefix_text = document.text[:line_start]
        suffix_text = document.text[line_end:]
        key = (len(doc_lines), row, prefix_text, suffix_text)
        if key != self._cached_key:
            other_words = set(self._WORD_RE.findall(prefix_text))
            other_words.update(self._WORD_RE.findall(suffix_text))
            self._other_words_sorted = sorted(other_words)
            self._cached_key = key

        neg_len = -len(word_before_cursor)
        yielded = {word_before_cursor}
        for w in sorted(set(self._WORD_RE.findall(doc_lines[row]))):
            if w.startswith(word_before_cursor) and w not in yielded:
                yielded.add(w)
                yield Completion(w, start_position=neg_len)

        words = self._other_words_sorted
        lo = bisect.bisect_left(words, word_before_cursor)
        n = len(words)
        while lo < n and words[lo].startswith(word_before_cursor):
            w = words[lo]
            if w not in yielded:
                yield Completion(w, start_position=neg_len)
            lo += 1


def bench_thai_plan() -> None:
    print("=== 1. Thai & Lao Cell-Cluster / Syllable Verification & Benchmarks ===")
    assert len(_THAI_COMBINING_CPS) == 34, "Expected 16 Thai + 18 Lao combining marks"
    for cp in (0x0EBA, 0x0EC7, 0x0ECE):
        assert is_thai_combining(cp), f"Missing Lao combining mark U+{cp:04X}"
        assert is_combining_char(chr(cp)), f"is_combining_char failed for U+{cp:04X}"
    assert is_combining_char("\u0301"), "Expected Latin combining acute U+0301 to be combining"

    # Verify prev_cell_offset from both cell boundaries and mid-cluster positions:
    assert prev_cell_offset("ที่ดิน", 4, 1) == 3, "Mid-cluster col=4 on ที่ดิน must snap to 3, not 0"
    assert prev_cell_offset("ที่ดิน", 3, 1) == 0
    assert prev_cell_offset("ที่ดิน", 5, 1) == 3

    samples = [
        ("ที่ดิน", [0, 3, 5, 6], 3),
        ("ผู้ใหญ่", [0, 3, 4, 5, 7], 3),
        ("เกาะ", [0, 1, 2, 3, 4], 4),
        ("น้ำ", [0, 2, 3], 3),
        ("กำ", [0, 1, 2], 2),
        ("ธรรม", [0, 1, 2, 3, 4], 3),  # Ro Han (ธรร = 3 codepoints, followed by ม)
        ("ดีๆ", [0, 2, 3], 3),  # Right-attaching ๆ attached to preceding syllable ดี
        ("ๆฯ", [0, 1, 2], 1),  # Standalone right-attaching symbols
        ("ທີ່ດິນ", [0, 3, 5, 6], 3),  # Lao: ທ + ◌ີ + ◌່ | ດ + ◌ິ | ນ
    ]
    for word, expected_stops, expected_first_cluster_end in samples:
        actual = cell_stops(word)
        assert actual == expected_stops, f"{word}: expected {expected_stops}, got {actual}"
        # Verify reverse traversal via prev_cell_offset matches cell_starts in reverse:
        rev_starts: list[int] = []
        c = len(word)
        while c > 0:
            c = prev_cell_offset(word, c, 1)
            rev_starts.append(c)
        assert rev_starts[::-1] == actual[:-1], (
            f"{word}: reverse starts {rev_starts[::-1]} != {actual[:-1]}"
        )
        cluster_end = find_thai_cluster_end(word, 0)
        assert cluster_end == expected_first_cluster_end, (
            f"{word}: expected first syllable end {expected_first_cluster_end}, got {cluster_end}"
        )
        print(
            f"  {word!r:<10} len={len(word)} cells={len(actual) - 1} "
            f"cell_starts={actual[:-1]} stops={actual} first_syllable_end={cluster_end}"
        )

    ascii_line = "def calculate_cursor_position(document, count=1): return 0"
    thai_line = "การเดินทางในที่ดินของผู้ใหญ่บ้านและการพัฒนาโปรแกรมภาษาไทยในเทอร์มินัล"
    iters = 200_000

    t0 = time.perf_counter_ns()
    for _ in range(iters):
        next_cell_offset(ascii_line, 10, 1)
    ascii_ns = (time.perf_counter_ns() - t0) / iters

    t0 = time.perf_counter_ns()
    for _ in range(iters):
        next_cell_offset(thai_line, 12, 1)
    thai_ns = (time.perf_counter_ns() - t0) / iters

    print(f"  next_cell_offset (ASCII fast-path): {ascii_ns:.1f} ns/call")
    print(f"  next_cell_offset (Thai cluster):    {thai_ns:.1f} ns/call\n")


def bench_speed_plan() -> None:
    print("=== 2. Speed & Latency Plan Verification & Micro-Benchmarks ===")
    pyvim_completion = importlib.import_module("pyvim.completion")
    pyvim_lexer = importlib.import_module("pyvim.lexer")
    pyvim_style = importlib.import_module("pyvim.style")
    from pygments.styles import get_all_styles

    DocumentWordsCompleter = pyvim_completion.DocumentWordsCompleter
    DocumentLexer = pyvim_lexer.DocumentLexer
    generate_built_in_styles = pyvim_style.generate_built_in_styles
    get_editor_style_by_name = pyvim_style.get_editor_style_by_name

    # P2: Measure cold-startup Style initialization first (before Pygments warms importlib.metadata)
    t0 = time.perf_counter()
    style_names = list(get_all_styles())
    p2_get_all_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    styles = generate_built_in_styles()
    p2_eager_ms = p2_get_all_ms + (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    lazy_styles = _LazyStylesDict(get_editor_style_by_name)
    _ = get_editor_style_by_name("vim")
    p2_startup_ms = (time.perf_counter() - t0) * 1000
    assert len(lazy_styles) == len(style_names) == len(styles)

    # Build a 4,000-line Python file including a 50-line multiline docstring spanning lines 80..130:
    lines: list[str] = []
    for i in range(2000):
        if i == 40:
            lines.append('def doc_func():\n    """start multiline docstring')
        elif 40 < i < 65:
            lines.append(f"    inside multiline docstring {i}\n    still string {i}")
        elif i == 65:
            lines.append('    end multiline docstring"""\n    return 42')
        else:
            lines.append(f"def func_{i}(x, y):\n    return x * {i} + y  # comment {i}")
    text = "\n".join(lines)
    doc = Document(text, cursor_position=0)
    _ = doc.lines

    eb = _DummyEditorBuffer("sample.py")
    uncached_lexer = DocumentLexer(eb)
    streaming_lexer = _PublicStreamingDocumentLexer(eb)

    # Verify 100% token parity across the multiline docstring (lines 75..140):
    ref_get_line = PygmentsLexer.from_filename("sample.py", sync_from_start=False).lex_document(doc)
    stream_get_line = streaming_lexer.lex_document(doc)
    for row in range(75, 140):
        assert stream_get_line(row) == ref_get_line(row), (
            f"Token mismatch at multiline string row {row}"
        )
    print("  Verified P1 multiline docstring token parity (lines 75..140): PASS")

    # P1a: Top 40 lines of 4,000-line file
    t0 = time.perf_counter()
    for _ in range(10):
        get_line = uncached_lexer.lex_document(doc)
        for row in range(40):
            get_line(row)
    p1_top_uncached_ms = (time.perf_counter() - t0) / 10 * 1000

    t0 = time.perf_counter()
    for _ in range(20):
        get_line = streaming_lexer.lex_document(doc)
        for row in range(40):
            get_line(row)
    p1_top_cached_ms = (time.perf_counter() - t0) / 20 * 1000
    print(
        f"  P1a DocumentLexer (top 40 lines of 4000-line file): "
        f"current={p1_top_uncached_ms:.2f} ms -> cached+streaming={p1_top_cached_ms:.2f} ms"
    )

    # P1b: Middle 40 lines (@ line 2000) of 4,000-line file
    t0 = time.perf_counter()
    for _ in range(10):
        get_line = uncached_lexer.lex_document(doc)
        for row in range(2000, 2040):
            get_line(row)
    p1_mid_uncached_ms = (time.perf_counter() - t0) / 10 * 1000

    t0 = time.perf_counter()
    for _ in range(20):
        get_line = streaming_lexer.lex_document(doc)
        for row in range(2000, 2040):
            get_line(row)
    p1_mid_cached_ms = (time.perf_counter() - t0) / 20 * 1000
    print(
        f"  P1b DocumentLexer (middle 40 lines @ 2000 of 4000-line file): "
        f"current={p1_mid_uncached_ms:.2f} ms -> cached+streaming={p1_mid_cached_ms:.2f} ms"
    )

    # P1c: Bottom 40 lines of 4,000-line file
    t0 = time.perf_counter()
    for _ in range(20):
        get_line = uncached_lexer.lex_document(doc)
        for row in range(3960, 4000):
            get_line(row)
    p1_bot_uncached_ms = (time.perf_counter() - t0) / 20 * 1000

    t0 = time.perf_counter()
    for _ in range(20):
        get_line = streaming_lexer.lex_document(doc)
        for row in range(3960, 4000):
            get_line(row)
    p1_bot_cached_ms = (time.perf_counter() - t0) / 20 * 1000
    print(
        f"  P1c DocumentLexer (bottom 40 lines of 4000-line file): "
        f"current={p1_bot_uncached_ms:.2f} ms -> cached+streaming={p1_bot_cached_ms:.2f} ms"
    )

    print(
        f"  P2 Style init ({len(styles)} styles): "
        f"cold_eager={p2_eager_ms:.2f} ms (cold get_all_styles={p2_get_all_ms:.2f} ms) "
        f"-> deferred _LazyStylesDict startup={p2_startup_ms:.2f} ms"
    )

    # P3: DocumentWordsCompleter fresh vs singleton line-cached
    docs = []
    for i in range(20):
        s = text + f"\ndef my_var_{i}"
        d = Document(s, cursor_position=len(s))
        _ = d.lines
        docs.append(d)
    ev = CompleteEvent()

    t0 = time.perf_counter()
    for d in docs:
        list(DocumentWordsCompleter().get_completions(d, ev))
    p3_uncached_ms = (time.perf_counter() - t0) / len(docs) * 1000

    singleton_comp = _SingletonCachedWordsCompleter()
    list(singleton_comp.get_completions(docs[0], ev))  # warm non-cursor lines
    t0 = time.perf_counter()
    for d in docs:
        list(singleton_comp.get_completions(d, ev))
    p3_cached_ms = (time.perf_counter() - t0) / len(docs) * 1000
    print(
        f"  P3 DocumentWordsCompleter (4000 lines, typing on current line): "
        f"fresh={p3_uncached_ms:.2f} ms -> singleton_cached={p3_cached_ms:.3f} ms"
    )


if __name__ == "__main__":
    print(
        f"Python {platform.python_version()} ({platform.machine()}), "
        f"prompt_toolkit {prompt_toolkit.__version__}\n"
    )
    bench_thai_plan()
    bench_speed_plan()
