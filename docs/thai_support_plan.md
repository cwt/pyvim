---
type: architecture_guideline
title: "Thai & Lao Script Support Plan for pyvim"
description: "Detailed root-cause analysis, cell-cluster architecture (adapted from szn), Sara Am differential rendering refresh, version-gated prompt_toolkit integration, and test matrix for Thai/Lao in pyvim - IMPLEMENTED and machine-verified."
status: stable
sources:
  - ../setup.py
  - ../pyvim/thai.py
  - ../pyvim/editor.py
  - ../pyvim/editor_buffer.py
  - ../pyvim/key_bindings.py
  - ../pyvim/layout.py
  - ../tools/bench_plans.py
  - ../tests/test_thai.py
verified: machine-confirmed
stale_after: 2027-01-01T00:00:00Z
tags: [thai, lao, unicode, sara-am, cursor-movement, vi-mode, prompt-toolkit, szn, implemented]
generated:
  by: "Antigravity (Gemini 4 Argon)"
  at: "2026-11-06T08:00:00Z"
timestamp: 2026-11-06T08:00:00Z
---

# Thai & Lao Script Support Plan for `pyvim`

This document specifies the root causes of broken Thai/Lao cursor navigation, editing, and terminal rendering in `pyvim`, and details how to adapt the cell-cluster and renderer architecture from `szn` (`src/thai.zig`, `src/grid.zig`, `src/mode_copy.zig`, `src/server/render.zig`) into `pyvim` with sub-microsecond (`< 1 µs`) per-keypress overhead[^src-thai][^src-key-bindings][^src-layout][^src-bench]. **Status: all of Phases 1–4 are implemented and machine-verified** (`pyvim/thai.py`, `pyvim/key_bindings.py`, `pyvim/editor.py`, and 13 unit tests in `tests/test_thai.py`[^src-test-thai], 68 total tests passing, Python 3.10+ AST and mypy clean).

---

## 1. Problem Statement & Granularity Model: Cell Clusters vs. Syllables

In Thai (`U+0E00..U+0E7F`) and Lao (`U+0E80..U+0EFF`) scripts, there are **two distinct structural units** that a terminal Vi editor must distinguish:

1. **Terminal Cell Cluster (`base + comb*`)**:
   A single visual character column on the terminal grid consists of one **spacing base character** (`width == 1`) followed by **0 to 2 zero-width combining marks** (`GC=Mn`, `width == 0`: upper/lower vowels, tone marks, cancellation marks).
   * Leading vowels (`เ`, `แ`, `โ`, `ใ`, `ไ`), following vowels (`ะ`, `า`, `ำ`, `ๅ`), standalone symbols (`ๆ`, `ฯ`), and base consonants (`ก`–`ฮ`) are all `GC=Lo` spacing characters (`width == 1`) that occupy their own terminal cell.
2. **Orthographic Syllable / Word (`[leading_vowel] + base (+ optional รร) + [following_vowel*] + [right_attaching*]` or dictionary word)**:
   A Thai syllable or word frequently spans **multiple terminal cells** (e.g., `"เกาะ"` spans 4 cells; `"น้ำ"` spans 2 cells; `"ธรรม"` spans 4 cells across `"ธรร"` + `"ม"`; `"ผู้ใหญ่"` spans 4 cells across 2 syllables).

### 1.1 Which Vi Motions & Operators Use Which Unit?

Following `szn`'s copy-mode design (`src/mode_copy.zig`), character-wise motions/edits operate on **Cell Clusters**, whereas word-wise motions/text-objects operate on **Syllable / Word Boundaries**:

| Granularity Unit | Vi Motions & Operators | Behavior on Thai/Lao Text |
| :--- | :--- | :--- |
| **Cell Cluster (`base + comb*`)** | `h`, `l`, `<Left>`, `<Right>`, `<Space>`, `<Backspace>`, `0`, `^`, `$`, `j`, `k`, `<Esc>`, `a`, `x`, `X`, `s`, `r<char>`, `~`, `dh`, `dl`, `ch`, `cl`, `yh`, `yl` | Steps or mutates **1 visual terminal cell** at a time. Never parks the cursor on a zero-width combining mark (`GC=Mn`) and never slices a cell cluster in half. |
| **Syllable / Word (`find_thai_word_breaks`)** | `w`, `b`, `e`, `W`, `B`, `E`, `dw`, `cw`, `yw`, `diw`, `ciw`, `yiw`, `daw`, `caw`, `yaw`, `*`, `#` | Steps or operates across **1 Thai word** (Tier 1: `libthai` `th_brk_wc_find_breaks` dictionary segmentation) or **1 orthographic syllable cluster** (Tier 2 fallback: `find_thai_cluster_end`). |

### 1.2 Concrete Walkthroughs Across Canonical Thai & Lao Cases

All cell starts (`cell_starts`), full stop lists including EOL (`stops`), reverse `prev_cell_offset` traversals, and first syllable ends (`first_syllable_end`) below are verified by `tools/bench_plans.py`[^src-bench]:

| Sample Word | Codepoints (`len`) | Visual Cells (`wcswidth`) | `cell_starts` (Normal-mode valid cursor cols) | `stops` (`h`/`l` step offsets + EOL) | Syllable / Word Boundaries (`w`/`b`/`e`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`"ที่ดิน"`** ("land") | `6` (`ท`, `◌ี`, `◌่`, `ด`, `◌ิ`, `น`) | `3` (`ที่` \| `ดิ` \| `น`) | `[0, 3, 5]` | `[0, 3, 5, 6]` (3 cell steps) | Tier 1 (`libthai`): `[0, 6]` (or `[0, 3, 6]`); Tier 2: first syllable end `3` (`[0, 3, 5, 6]`) |
| **`"ผู้ใหญ่"`** ("adult") | `7` (`ผ`, `◌ู`, `◌้`, `ใ`, `ห`, `ญ`, `◌่`) | `4` (`ผู้` \| `ใ` \| `ห` \| `ญ่`) | `[0, 3, 4, 5]` | `[0, 3, 4, 5, 7]` (4 cell steps) | Tier 1 (`libthai`): `[0, 7]`; Tier 2: first syllable end `3` (`[0, 3, 5, 7]`) |
| **`"เกาะ"`** ("island") | `4` (`เ`, `ก`, `า`, `ะ`) | `4` (`เ` \| `ก` \| `า` \| `ะ`) | `[0, 1, 2, 3]` | `[0, 1, 2, 3, 4]` (**4 cell steps** for `h`/`l`) | Tier 1 & Tier 2: **`[0, 4]` (1 syllable step** for `w`/`b`/`e`) |
| **`"น้ำ"`** ("water", Sara Am) | `3` (`น`, `◌้`, `ำ`) | `2` (`น้` \| `ำ`) | `[0, 2]` | `[0, 2, 3]` (2 cell steps: `น้` then `ำ`) | Tier 1 & Tier 2: **`[0, 3]` (1 syllable step** for `w`/`b`/`e`) |
| **`"กำ"`** ("hold", Sara Am) | `2` (`ก`, `ำ`) | `2` (`ก` \| `ำ`) | `[0, 1]` | `[0, 1, 2]` (2 cell steps: `ก` then `ำ`) | Tier 1 & Tier 2: **`[0, 2]` (1 syllable step** for `w`/`b`/`e`) |
| **`"ธรรม"`** ("dharma", Ro Han) | `4` (`ธ`, `ร`, `ร`, `ม`) | `4` (`ธ` \| `ร` \| `ร` \| `ม`) | `[0, 1, 2, 3]` | `[0, 1, 2, 3, 4]` (4 cell steps) | Tier 2 (`find_thai_cluster_end`): consumes `ธรร` as `[0, 3]`, then `ม` `[3, 4]` |
| **`"ดีๆ"`** (right-attaching `ๆ`) | `3` (`ด`, `◌ี`, `ๆ`) | `2` (`ดี` \| `ๆ`) | `[0, 2]` | `[0, 2, 3]` (2 cell steps) | Tier 2 (`find_thai_cluster_end`): attaches trailing `ๆ` to `ดี` $\rightarrow$ `[0, 3]` |
| **`"ๆฯ"`** (standalone symbols) | `2` (`ๆ` `U+0E46`, `ฯ` `U+0E2F`) | `2` (`ๆ` \| `ฯ`) | `[0, 1]` | `[0, 1, 2]` (2 cell steps) | Standalone right-attaching symbols at cluster start return single cell (`[0, 1, 2]`) |
| **`"ທີ່ດິນ"`** (Lao "land") | `6` (`ທ`, `◌ີ`, `◌່`, `ດ`, `◌ິ`, `ນ`) | `3` (`ທີ່` \| `ດິ` \| `ນ`) | `[0, 3, 5]` | `[0, 3, 5, 6]` (3 cell steps) | Tier 2: first syllable end `3` (`[0, 3, 5, 6]`) |

### 1.3 Special Case: Thai/Lao SARA AM (`U+0E33` `ำ` / `U+0EB3` `ຳ`)

`SARA AM` (`U+0E33` Thai `ำ`, `U+0EB3` Lao `ຳ`) requires explicit attention across both the cell model and the terminal diff renderer (ported from `szn` commit `71ba808` / `szn/src/server/render.zig:664-694`):

1. **Unicode Category & Cell Width**:
   * `U+0E33` and `U+0EB3` have General Category `Lo` (Letter, Other), **not** `Mn` (Mark, Nonspacing). Thus `is_thai_combining(0x0E33)` is `False`, `is_sara_am(0x0E33)` is `True`, and `is_thai_following_vowel(0x0E33)` is `True`.
   * Both Python's `wcwidth.wcwidth('\u0e33')` and `prompt_toolkit.utils.get_cwidth('\u0e33')` return **`1`** (matching `szn/src/char_width.zig:248-250`, Unicode East Asian Width Neutral, and Alacritty).
   * Consequently, in `"น้ำ"` (`น` + `◌้` + `ำ`), Cell 0 (`x = 0`) holds `"น้"` (`[0:2]`) and Cell 1 (`x = 1`) holds `"ำ"` (`[2:3]`).
2. **Cross-Cell Nikhahit Shaping & Differential Rendering Bug**:
   * Visually, `ำ` (`U+0E33`) is rendered by terminal font shapers (e.g., Kitty, WezTerm, Ghostty with Thai fonts such as Tlwg Typo) by projecting its leading NIKKAHIT circle (`◌ํ`) **leftward onto the preceding cell `x - 1`** while drawing the `า` stem in cell `x`.
   * Module-level function `prompt_toolkit.renderer._output_screen_diff` (`prompt_toolkit/renderer.py:40`, with its per-column diff loop at `renderer.py:196-225`, called by `Renderer.render` at `renderer.py:698`) only emits cells where `new_char.char != old_char.char or new_char.style != old_char.style`.
   * **Bug A (Deleting/Modifying `ำ` at `x`)**: When `ำ` at column `x` is deleted (e.g., pressing `x` on `ำ` in `"กำ"`), `new_row[x - 1]` (`'ก'`) is unchanged in `Screen.data_buffer`, so `_output_screen_diff` only redraws column `x`. The terminal clears the shaped ligature across `x - 1..x`, leaving the preceding consonant at `x - 1` blank on screen!
   * **Bug B (Modifying Preceding Consonant at `x - 1`)**: When the consonant at `x - 1` changes (e.g., `rข` changing `'ก'` to `'ข'` before `'ำ'`), `new_row[x]` (`'ำ'`) is unchanged in `Screen.data_buffer`, so `_output_screen_diff` only redraws `x - 1`. Because `'ำ'` at `x` is not re-emitted, the terminal fails to project the NIKKAHIT circle onto the new consonant `'ข'`!
   * **Fix (Phase 4)**: Wrap `prompt_toolkit.renderer._output_screen_diff` (which receives `screen`, `previous_screen`, and `size` directly at `renderer.py:40, 698`) to run `_sanitize_and_invalidate_sara_am(screen, previous_screen, size.columns)` before the diff loop executes.

---

## 2. Root-Cause Audit: `prompt_toolkit` vs. `pyvim`

`pyvim` delegates its text buffer (`Document`, `Buffer`), Vi keybindings (`load_vi_bindings`), screen layout (`BufferControl`, `Window`), and differential terminal output (`_output_screen_diff`) to `prompt_toolkit` (`3.0.53` in the target environment, constrained to `>=2.0.0,<3.1.0` in `setup.py:20`[^src-setup])[^src-editor].

| Layer | File & Line (`prompt_toolkit 3.0.53`) | Current Implementation | Exact Failure Mode on Thai/Lao |
| :--- | :--- | :--- | :--- |
| **1. Cursor Left / Right** | `prompt_toolkit/document.py:695-711` | `get_cursor_left_position` returns `-min(self.cursor_position_col, count)`; `get_cursor_right_position` returns `min(count, len(self.current_line_after_cursor))`. | Moves by `±1` **codepoint** instead of `±1` **cell cluster**. Pressing `l` on `"ที่ดิน"` takes 6 presses instead of 3 and parks the cursor on zero-width marks `◌ี` (`idx=1`), `◌่` (`idx=2`), `◌ิ` (`idx=4`). |
| **2. Cursor Up / Down (`j` / `k`)** | `prompt_toolkit/document.py:713-754` | `get_cursor_up_position` / `get_cursor_down_position` call `translate_row_col_to_index(target_row, column)` using raw codepoint `column`. | Moving `j`/`k` from `col=2` on an ASCII line onto `"ที่ดิน"` lands at codepoint index `2` (`◌่`, inside Cell 0 `"ที่"`). |
| **3. Vi `x`, `X`, `s`, `r`, `~`, `$`** | `prompt_toolkit/key_binding/bindings/vi.py:837-845` (`s` `_substitute`), `929-938` (`x` `_delete`), `940-946` (`X` `_delete_before_cursor`), `1018-1028` (`~` `_reverse_case`), `1244-1249` (`$` `_dollar`), `1910-1917` (`r` `_replace_single`) | `x` (`_delete`) deletes `min(event.arg, len(current_line_after_cursor))` codepoints; `X` (`_delete_before_cursor`) deletes `min(event.arg, len(current_line_before_cursor))` codepoints; `s` (`_substitute`) deletes `event.arg` codepoints; `r` (`_replace_single`) overwrites 1 codepoint; `~` (`_reverse_case`) overwrites `1` codepoint (`current_char`); `$` moves to `len(line)`. | Pressing `x` on `"ที่"` deletes only `ท` (`U+0E17`), orphaning `◌ี` and `◌่` so they attach to the preceding character or render as dotted circles. Pressing `~` on `"ที่"` advances `cursor_position` by `1` onto `◌ี`. |
| **4. Vi Word Regex (`w`/`b`/`e`)** | `prompt_toolkit/document.py:28-32` | `_FIND_WORD_RE = re.compile(r"([a-zA-Z0-9_]+|[^a-zA-Z0-9_\s]+)")` (and line 31 `_FIND_CURRENT_WORD_INCLUDE_TRAILING_WHITESPACE_RE` with trailing `\s*`) | Hardcodes ASCII `[a-zA-Z0-9_]+`. Every Thai/Lao character matches `[^a-zA-Z0-9_\s]+`, so an entire unspaced Thai sentence is treated as **one giant non-word token**. |
| **5. Screen Copy & Diff Renderer** | `prompt_toolkit/layout/containers.py:2046-2082`, `prompt_toolkit/renderer.py:40, 196-225, 698` | `Window._copy_body` writes `new_buffer_row[x + xpos] = char` before merging `char_width == 0` into `x + xpos - pw`; module-level `_output_screen_diff` diffs cells independently without checking `SARA AM` (`U+0E33`/`U+0EB3`). | For `BufferControl`, `get_line()` (`controls.py:785`) appends `" "`, overwriting the stray mark at EOL and keeping `rowcol_to_yx` / `yx_to_rowcol` aligned on cell starts. However, `FormattedTextControl` (status/tab bars) and soft-wrapped lines retain a stray `width == 0` mark at `x + xpos`, and `_output_screen_diff` fails to refresh the neighbor cell when `SARA AM` or its preceding consonant changes. |

---

## 3. Architecture Adapted from `szn` & Reproducible Performance

### 3.1 Porting `szn/src/thai.zig` to `pyvim/thai.py`

We create a dedicated module `pyvim/thai.py` ported from `szn/src/thai.zig:6-135, 263-326, 700-792`:

```python
from __future__ import annotations

import ctypes
import threading
import unicodedata
from prompt_toolkit.utils import get_cwidth

# Complete 34-codepoint set of Thai (16) and Lao (18) GC=Mn combining marks,
# matching `szn/src/thai.zig:28-70` (`isThaiCombining`) 1-for-1.
# Note: SARA AM (U+0E33 / U+0EB3) is GC=Lo (spacing following vowel, width 1), NOT Mn.
_THAI_COMBINING_CPS: frozenset[int] = frozenset({
    # Thai combining marks (16 marks: U+0E31, U+0E34..U+0E3A, U+0E47..U+0E4E)
    0x0E31,                                     # MAI HAN-AKAT
    0x0E34, 0x0E35, 0x0E36, 0x0E37,             # SARA I, II, UE, UEE
    0x0E38, 0x0E39, 0x0E3A,                     # SARA U, UU, PHINTHU
    0x0E47,                                     # MAITAIKHU
    0x0E48, 0x0E49, 0x0E4A, 0x0E4B,             # MAI EK, THO, TRI, CHATTAWA
    0x0E4C, 0x0E4D, 0x0E4E,                     # THANTHAKHAT, NIKHAHIT, YAMAKKAN
    # Lao combining marks (18 marks: U+0EB1, U+0EB4..U+0EBC, 0x0EC7..0x0ECE)
    0x0EB1,                                     # MAI KAN
    0x0EB4, 0x0EB5, 0x0EB6, 0x0EB7,             # SARA I, II, Y, YY
    0x0EB8, 0x0EB9, 0x0EBA, 0x0EBB, 0x0EBC,     # SARA U, UU, PALI VIRAMA, MAI KON, LO
    0x0EC7,                                     # MAITAIKHU
    0x0EC8, 0x0EC9, 0x0ECA, 0x0ECB,             # MAI EK, THO, TI, CATAWA
    0x0ECC, 0x0ECD, 0x0ECE,                     # CANCELLATION MARK, NIKHAHIT, YAMAKKAN
})


def is_thai_or_lao(cp: int) -> bool:
    """True if cp is in the Thai (U+0E00..U+0E7F) or Lao (U+0E80..U+0EFF) blocks."""
    return 0x0E00 <= cp <= 0x0EFF


def is_thai_combining(cp: int) -> bool:
    """True if cp is one of the 34 Thai/Lao zero-width combining marks (GC=Mn)."""
    return cp in _THAI_COMBINING_CPS


def is_combining_char(ch: str) -> bool:
    """
    Fast-path check for Thai/Lao combining marks (`_THAI_COMBINING_CPS`),
    with general Unicode `Mn` / `get_cwidth(ch) == 0` fallback for other scripts.
    """
    cp = ord(ch)
    if 0x0E00 <= cp <= 0x0EFF:
        return cp in _THAI_COMBINING_CPS
    if cp < 0x0300:
        return False
    return unicodedata.category(ch) == "Mn" or get_cwidth(ch) == 0


def is_sara_am(cp: int) -> bool:
    """True if cp is Thai SARA AM (U+0E33) or Lao SARA AM (U+0EB3)."""
    return cp == 0x0E33 or cp == 0x0EB3


def is_thai_leading_vowel(cp: int) -> bool:
    """True if cp is a visual-order leading vowel (U+0E40..U+0E44, U+0EC0..U+0EC4)."""
    return (0x0E40 <= cp <= 0x0E44) or (0x0EC0 <= cp <= 0x0EC4)


def is_thai_following_vowel(cp: int) -> bool:
    """True if cp is a Thai/Lao following vowel (ะ, ั, า, ำ, ๅ / ະ, ັ, າ, ຳ)."""
    return cp in (
        0x0E30, 0x0E31, 0x0E32, 0x0E33, 0x0E45,
        0x0EB0, 0x0EB1, 0x0EB2, 0x0EB3,
    )


def is_thai_right_attaching(cp: int) -> bool:
    """True if cp is a right-attaching symbol (ฯ U+0E2F, ๆ U+0E46, ຯ U+0EAF, ໆ U+0EC6)."""
    return cp in (0x0E2F, 0x0E46, 0x0EAF, 0x0EC6)


def is_thai_base(cp: int) -> bool:
    """
    Port of `szn/src/thai.zig:126-133` (`isThaiBase`):
    True if cp is a width-1 Thai/Lao codepoint that is not a combining mark,
    leading vowel, following vowel, or right-attaching mark.
    """
    return (
        is_thai_or_lao(cp)
        and not is_thai_combining(cp)
        and not is_thai_leading_vowel(cp)
        and not is_thai_following_vowel(cp)
        and not is_thai_right_attaching(cp)
        and get_cwidth(chr(cp)) == 1
    )
```

### 3.2 `O(1)` Local Cell-Cluster Boundary Scanners

 Note how `prev_cell_offset` uses a **single** backward loop (`idx -= 1; while idx > 0 and is_combining_char(line[idx]): idx -= 1`) without a pre-snap loop: if `col` is already mid-cluster (e.g. `col=4` on `"ที่ดิน"`, which is `◌ิ` inside Cell 1 `"ดิ"` at `[3:5]`), one backward step lands at `3` (`ด`, the start of the enclosing cell) rather than skipping all the way to `0`[^src-bench]:

```python
def snap_to_cell_start(line: str, col: int) -> int:
    """
    If `col` is parked on a combining mark inside `line` (e.g. after vertical `j`/`k`
    motion), walk backward to the base character of the enclosing cell cluster.
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
    """
    Move `count` visual cell clusters backward from `col` within `line`.
    Returns the new column index in `0..len(line)`.
    """
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
```

### 3.3 Two-Tier Syllable / Word Breaking (`w`, `b`, `e`)

Ported directly from `szn/src/thai.zig:285-326` (`findThaiClusterEnd`) and `szn/src/thai.zig:700-792` (`getLibThai`):

1. **Tier 1 (`libthai` via `ctypes`, optional runtime `dlopen`)**:
   * Guarded by a module-level `_libthai_lock = threading.Lock()` and `_libthai_initialized = False`.
   * Probes the 16 library paths from `szn/src/thai.zig:713-730` (`/opt/homebrew/lib/libthai.dylib`, `/usr/local/lib/libthai.dylib`, `libthai.so.0`, etc.).
   * Resolves the three C symbols used by `szn/src/thai.zig:733-744`:
     * `th_brk_new(None) -> c_void_p`
     * `th_brk_wc_find_breaks(brk, wchar_buf, pos_buf, max_breaks) -> c_int`
     * `th_brk_delete(brk) -> None`
2. **Tier 2 (`find_thai_cluster_end` TCC-lite heuristic fallback, `szn/src/thai.zig:285-326`)**:
   * Matches `szn`'s `findThaiClusterEnd` cell-cluster grammar (`[leading_vowel] + base (+ optional Ro Han รร) + [following_vowel*] + [right_attaching*]`):
     ```python
     def find_thai_cluster_end(line: str, start: int) -> int:
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

         # Check for Thai Ro Han (รร, U+0E23 + U+0E23) following the base consonant
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
     ```
   * Handles multiple following vowels (`"เกาะ"` $\rightarrow$ `[0, 4]`), `SARA AM` (`"น้ำ"` $\rightarrow$ `[0, 3]`), Ro Han (`"ธรรม"` $\rightarrow$ `"ธรร"` `[0, 3]` + `"ม"` `[3, 4]`), trailing right-attaching marks (`"ดีๆ"` $\rightarrow$ `[0, 3]`), and standalone right-attaching symbols at cluster start (`"ๆฯ"` $\rightarrow$ `[0, 1]`, `[1, 2]`).

### 3.3b Implementation refines §3.2/§3.3 (2026-11-06, hg rev 169)

The shipped implementation has drifted beyond the plan snippets above, by design:

* `next_cell_offset` clamps negative/degenerate inputs (`count <= 0` returns
  `n if col >= n else max(0, col)`); `prev_cell_offset` returns
  `min(col, len(line))` for non-moving steps.
* Word motions are **line-local**: `_word_spans_for_line` (an `lru_cache`
  keyed on the line text) replaced whole-document scans — `:w` on a 2.4 MB
  Thai file dropped from ~640 ms to ~0.4 ms cold / ~0.4 µs warm
  (see `docs/bugs/001.md`).

### 3.4 Reproducible Micro-Benchmarks (`tools/bench_plans.py`)

Running `python tools/bench_plans.py` confirms all cell stops, reverse `prev_cell_offset` walks, and syllable cluster ends, and measures sub-microsecond (`< 1 µs`) call latency (`~50–75 ns` ASCII / `~310 ns` Thai on macOS arm64 Python 3.15; `~430 ns` ASCII / `~570 ns` Thai on Linux x86_64 Python 3.12)[^src-bench]:

```text
=== 1. Thai & Lao Cell-Cluster / Syllable Verification & Benchmarks ===
  'ที่ดิน'   len=6 cells=3 cell_starts=[0, 3, 5] stops=[0, 3, 5, 6] first_syllable_end=3
  'ผู้ใหญ่'  len=7 cells=4 cell_starts=[0, 3, 4, 5] stops=[0, 3, 4, 5, 7] first_syllable_end=3
  'เกาะ'     len=4 cells=4 cell_starts=[0, 1, 2, 3] stops=[0, 1, 2, 3, 4] first_syllable_end=4
  'น้ำ'      len=3 cells=2 cell_starts=[0, 2] stops=[0, 2, 3] first_syllable_end=3
  'กำ'       len=2 cells=2 cell_starts=[0, 1] stops=[0, 1, 2] first_syllable_end=2
  'ธรรม'     len=4 cells=4 cell_starts=[0, 1, 2, 3] stops=[0, 1, 2, 3, 4] first_syllable_end=3
  'ดีๆ'      len=3 cells=2 cell_starts=[0, 2] stops=[0, 2, 3] first_syllable_end=3
  'ๆฯ'       len=2 cells=2 cell_starts=[0, 1] stops=[0, 1, 2] first_syllable_end=1
  'ທີ່ດິນ'   len=6 cells=3 cell_starts=[0, 3, 5] stops=[0, 3, 5, 6] first_syllable_end=3
  next_cell_offset (ASCII fast-path): 51.8 ns/call
  next_cell_offset (Thai cluster):    313.5 ns/call
```

---

## 4. Detailed Implementation Plan & Version-Gated `prompt_toolkit` Integration

### 4.1 Architectural Safeguard: Version Gating & Fallbacks (`prompt_toolkit >=2.0.0,<3.1.0`)

Because `setup.py:20` declares `prompt_toolkit>=2.0.0,<3.1.0`[^src-setup], `install_prompt_toolkit_thai_patches()` in `pyvim/thai.py` (called once from `Editor.__init__` in `pyvim/editor.py`[^src-editor]) guards every hook with:
1. **Explicit attribute and `inspect.signature` checks** before wrapping `Document.get_cursor_left_position`, `Document.get_cursor_right_position`, `Document.get_cursor_up_position`, `Document.get_cursor_down_position`, and `prompt_toolkit.renderer._output_screen_diff`.
2. **Startup self-test** verifying `Document("ที่ดิน", cursor_position=0).get_cursor_right_position(1) == 3`.
3. **Graceful fallback** restoring the original function and logging a warning if a future or non-standard `prompt_toolkit` build alters the expected signature.

### Phase 1: Create `pyvim/thai.py`
Implement:
1. Character classification predicates: `is_thai_or_lao`, `is_thai_combining` (all 34 Thai/Lao `Mn` marks), `is_combining_char` (with Unicode `Mn`/`get_cwidth == 0` fallback), `is_sara_am`, `is_thai_leading_vowel`, `is_thai_following_vowel`, `is_thai_right_attaching`, `is_thai_base`.
2. Cell-cluster boundary scanners: `snap_to_cell_start`, `next_cell_offset`, `prev_cell_offset`.
3. Two-tier word/syllable segmentation: `find_thai_cluster_end`, `find_thai_word_breaks` (`th_brk_new` / `th_brk_wc_find_breaks` / `th_brk_delete`), and Thai-aware `find_next_word_beginning`, `find_next_word_ending`, `find_previous_word_beginning`, `find_previous_word_ending`, `get_word_under_cursor`.

### Phase 2: Cell-Cluster Cursor Movement on `Document` (`h`, `l`, `j`, `k`, `a`, `<Esc>`)

Wrap `Document.get_cursor_left_position`, `Document.get_cursor_right_position`, `Document.get_cursor_up_position`, and `Document.get_cursor_down_position` in `install_prompt_toolkit_thai_patches()`:

```python
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


def _doc_get_cursor_up_position(
    self: Document, count: int = 1, preferred_column: int | None = None
) -> int:
    assert count >= 1
    column = self.cursor_position_col if preferred_column is None else preferred_column
    target_row = max(0, self.cursor_position_row - count)
    target_line = self.lines[target_row]
    target_col = snap_to_cell_start(target_line, min(column, len(target_line)))
    return self.translate_row_col_to_index(target_row, target_col) - self.cursor_position


def _doc_get_cursor_down_position(
    self: Document, count: int = 1, preferred_column: int | None = None
) -> int:
    assert count >= 1
    column = self.cursor_position_col if preferred_column is None else preferred_column
    target_row = min(len(self.lines) - 1, self.cursor_position_row + count)
    target_line = self.lines[target_row]
    target_col = snap_to_cell_start(target_line, min(column, len(target_line)))
    return self.translate_row_col_to_index(target_row, target_col) - self.cursor_position
```

> [!NOTE]
> **What Phase 2 Covers vs. What Requires Phase 3**:
> Wrapping these four `Document` methods automatically fixes motions and operators that delegate to them in `prompt_toolkit/key_binding/bindings/vi.py`: `h`, `l`, `<Left>`, `<Right>`, `<Space>`, `<Backspace>`, `j`, `k`, `dh`, `dl`, `ch`, `cl`, `yh`, `yl`, `a` (which moves right by `get_cursor_right_position()`), and `<Esc>` (which moves left by `get_cursor_left_position()` when leaving Insert mode).
> However, **`x` (`_delete`), `X` (`_delete_before_cursor`), `s` (`_substitute`), `r` (`_replace_single`), `~` (`_reverse_case`), and `$` (`_dollar`) do NOT call `get_cursor_left/right_position`** — they slice raw codepoint counts directly in `vi.py` and therefore require explicit bindings in Phase 3.

### Phase 3: Cell-Cluster Vi Editing Bindings (`x`, `X`, `s`, `r`, `~`, `$`) & Precedence

In `pyvim/key_bindings.py`[^src-key-bindings], register Thai-aware Normal-mode handlers on `editor.key_bindings`:

1. **Why `pyvim/key_bindings.py` Precedence Wins Over `prompt_toolkit`'s `load_vi_bindings()`**:
   * In `prompt_toolkit/application/application.py:1487-1503`, `_CombinedRegistry._create_key_bindings` builds `[container_bindings..., self.app.key_bindings, page_navigation_bindings, self.app._default_bindings]` and reverses it (`key_bindings[::-1]`), placing `self.app.key_bindings` (`pyvim`) **after** `self.app._default_bindings` (`load_vi_bindings`).
   * In `prompt_toolkit/key_binding/key_processor.py:189`, `KeyProcessor` dispatches `matches[-1]` (the last matching binding in the merged registry). Therefore, a binding registered on `editor.key_bindings` with `filter=vi_navigation_mode` deterministically overrides `load_vi_bindings()`'s default handler.
2. **Exact Specifications for `x`, `X`, `s`, `r`, `~`, `$`**:
   * **`x` (overrides `_delete` at `vi.py:929-938`)**:
     Computes `end_col = next_cell_offset(doc.current_line, doc.cursor_position_col, event.arg)`, deletes `end_col - doc.cursor_position_col` codepoints (`buffer.delete(count=span)`), and stores the deleted cluster(s) in the clipboard.
   * **`X` (overrides `_delete_before_cursor` at `vi.py:940-946`)**:
     Computes `start_col = prev_cell_offset(doc.current_line, doc.cursor_position_col, event.arg)`, deletes `doc.cursor_position_col - start_col` codepoints before the cursor (`buffer.delete_before_cursor(count=span)`), and stores the deleted cluster(s) in the clipboard.
   * **`s` (overrides `_substitute` at `vi.py:837-845`)**:
     Deletes `next_cell_offset(doc.current_line, doc.cursor_position_col, event.arg) - doc.cursor_position_col` codepoints, stores them in the clipboard, and switches `vi_state.input_mode = InputMode.INSERT`.
   * **`r<char>` (overrides `_replace_single` at `vi.py:1910-1917`, `filter=vi_replace_single_mode`)**:
     Replaces `event.arg` cell clusters (`span = next_cell_offset(line, col, event.arg) - col`) with `event.data * event.arg`, steps back 1 cell cluster, and returns to `InputMode.NAVIGATION`.
   * **`~` (overrides `_reverse_case` at `vi.py:1018-1028`, `filter=vi_navigation_mode`)**:
     Extracts the current cell cluster `cluster = line[col : next_cell_offset(line, col, 1)]`, replaces that span with `cluster.swapcase()`, and advances `cursor_position` to `next_cell_offset` (so pressing `~` on `"ที่ดิน"` advances across `"ที่"` in 1 step instead of landing on `◌ี`).
   * **`$` in Navigation Mode (`filter=vi_navigation_mode & ~vi_waiting_for_text_object_mode`)**:
     Moves the cursor to the start of the **last cell cluster** on the current line: `prev_cell_offset(line, len(line), 1)`. Operator-pending `$` (`d$`, `c$`, `y$`, handled when `vi_waiting_for_text_object_mode` is active) is left untouched so `d$` continues to delete through `len(line)` including all trailing combining marks.

### Phase 4: Rendering Fix — Wrapping `prompt_toolkit.renderer._output_screen_diff`

#### 4.1 Why `Window._copy_body` Does Not Need Monkey-Patching for `rowcol_to_yx`
Inspecting `BufferControl.create_content` (`prompt_toolkit/layout/controls.py:785`) and `Window._copy_body` (`prompt_toolkit/layout/containers.py:2046-2082`) live against `prompt_toolkit 3.0.53` shows:
1. `BufferControl.get_line` appends a trailing space `[("", " ")]` (`width == 1`) to every line in a `BufferControl`.
2. For `"ที่ดิน"` (`len=6`, plus trailing `" "` at `col=6`), `Window._copy_body` produces:
   * `screen.data_buffer[0]`: `{0: 'ที่', 1: 'ดิ', 2: 'น', 3: ' '}` (the trailing `' '` overwrites the temporary `new_buffer_row[x + xpos] = char` combining mark).
   * `rowcol_to_yx`: `{(0, 0): (0, 0), (0, 1): (0, 1), (0, 2): (0, 1), (0, 3): (0, 1), (0, 4): (0, 2), (0, 5): (0, 2), (0, 6): (0, 3)}`.
   * At every cell-start offset (`col = 0, 3, 5` and EOL `6`), `rowcol_to_yx[0, col]` is **already** `(0, 0)`, `(0, 1)`, `(0, 2)`, `(0, 3)`.
   * For mouse clicks (`containers.py:1828`), `yx_to_rowcol = {v: k for k, v in rowcol_to_yx.items()}` evaluates to `{(0, 0): (0, 0), (0, 1): (0, 3), (0, 2): (0, 5), (0, 3): (0, 6)}` — mapping each screen column directly to the **base consonant index** of that cell!

#### 4.2 Exact Call Site: Wrapping `prompt_toolkit.renderer._output_screen_diff`
In `prompt_toolkit/renderer.py:698`, `Renderer.render` creates the new `screen = Screen()` locally (line 630) and passes both `screen` and `self._last_screen` into the module-level function `_output_screen_diff` (`prompt_toolkit/renderer.py:40`):

```python
        self._cursor_pos, self._last_style = _output_screen_diff(
            app,
            output,
            screen,
            self._cursor_pos,
            app.color_depth,
            self._last_screen,
            self._last_style,
            is_done,
            full_screen=self.full_screen,
            attrs_for_style_string=self._attrs_for_style,
            style_string_has_style=self._style_string_has_style,
            size=size,
            previous_width=(self._last_size.columns if self._last_size else 0),
        )
        self._last_screen = screen
```

Because `Renderer.render` resolves `_output_screen_diff` via `prompt_toolkit.renderer`'s module globals and immediately replaces `self._last_screen = screen` after `_output_screen_diff` returns (line 713), wrapping `prompt_toolkit.renderer._output_screen_diff` provides the exact `(screen, previous_screen, size)` arguments right before the diff loop (`renderer.py:196-225`) runs, and any poison cells written to `previous_screen` are automatically discarded at line 713:

```python
import inspect
import prompt_toolkit.renderer as ptk_renderer
from prompt_toolkit.layout.screen import Char, Screen

_SARA_AM_POISON = Char(char="\x00", style="__pyvim_sara_am_invalidate__")


def _cell_has_sara_am(cell: Char) -> bool:
    ch = cell.char
    return bool(ch) and ord(ch[0]) in (0x0E33, 0x0EB3)


def _sanitize_and_invalidate_sara_am(
    new_screen: Screen, previous_screen: Screen | None, width: int
) -> None:
    """
    1. Clear any stray zero-width combining mark cells (`cell.width == 0 and cell.char != ""`)
       left at the end of FormattedTextControl or wrapped lines.
    2. Port szn commit 71ba808 (`src/server/render.zig:664-694`): when Thai/Lao SARA AM
       (U+0E33 / U+0EB3) at column `x` or its preceding cell `x - 1` changes, poison the
       neighbor in `previous_screen` so `_output_screen_diff` re-emits both cells together.
    """
    for y, new_row in new_screen.data_buffer.items():
        # 1. Clear stray width-0 combining cells not overwritten by a trailing character.
        for x, cell in list(new_row.items()):
            if cell.width == 0 and cell.char != "":
                new_row[x] = Char(char=" ", style=cell.style)

        # 2. SARA AM neighbor invalidation for differential rendering.
        if previous_screen is None or y not in previous_screen.data_buffer:
            continue
        prev_row = previous_screen.data_buffer[y]
        max_x = min(
            width,
            max(new_row.keys(), default=0) + 1,
            max(prev_row.keys(), default=0) + 1,
        )
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


> **Implementation update (hg rev 170, 174)**: the shipped versions of
> `_sanitize_and_invalidate_sara_am` / `_install_renderer_patch` returned
> `bool`, use `setattr`, keep the original via `_pyvim_original`, guard
> `args[2]`/`args[5]` lengths, and the whole scan is gated by a sticky
> "session may render Thai" flag (`note_document_text`) so ASCII-only
> sessions skip it entirely (`docs/bugs/002.md`). The rollback in §4.1
> also restores both `KeyProcessor` patches (`docs/bugs/005.md`).

def _install_renderer_patch() -> None:
    orig_diff = getattr(ptk_renderer, "_output_screen_diff", None)
    if orig_diff is None or getattr(orig_diff, "_pyvim_thai_patched", False):
        return
    params = list(inspect.signature(orig_diff).parameters.keys())
    # Verify positional indices of `screen` (2) and `previous_screen` (5) and `size`:
    if len(params) < 12 or params[2] != "screen" or params[5] != "previous_screen":
        return

    def _wrapped_output_screen_diff(*args, **kwargs):
        screen = args[2]
        previous_screen = args[5]
        size = kwargs.get("size") or (args[11] if len(args) > 11 else None)
        width = size.columns if size is not None else 80
        _sanitize_and_invalidate_sara_am(screen, previous_screen, width)
        return orig_diff(*args, **kwargs)

    _wrapped_output_screen_diff._pyvim_thai_patched = True  # type: ignore[attr-defined]
    ptk_renderer._output_screen_diff = _wrapped_output_screen_diff
```

---

## 5. Verification & Unit Test Matrix (`tests/test_thai.py`)

We will add `tests/test_thai.py` covering every layer and edge case:

| Test Case | Input Text | Operation / Assertion | Expected Result |
| :--- | :--- | :--- | :--- |
| **`test_all_34_thai_lao_combining_marks`** | All 16 Thai + 18 Lao `Mn` marks (including `0x0EBA`, `0x0EC7`, `0x0ECE`) + Latin `U+0301` | `is_thai_combining` & `is_combining_char` | All 34 Thai/Lao marks return `True`; `is_combining_char("\u0301") == True`; `is_thai_combining(0x0E33) == False` |
| **`test_cell_offsets_thi_din_and_lao`** | `"ที่ดิน"` & Lao `"ທີ່ດິນ"` (`len=6`, 3 cells) | `cell_starts`, `stops`, & mid-cluster `prev_cell_offset("ที่ดิน", 4, 1)` | `cell_starts == [0, 3, 5]`, `stops == [0, 3, 5, 6]`, `prev_cell_offset("ที่ดิน", 4, 1) == 3` |
| **`test_cell_offsets_phu_yai`** | `"ผู้ใหญ่"` (`len=7`, 4 cells) | `cell_starts` & `stops` | `cell_starts == [0, 3, 4, 5]`, `stops == [0, 3, 4, 5, 7]` |
| **`test_cell_vs_syllable_ko_ro_han_mai_yamok`** | `"เกาะ"` (`len=4`), `"ธรรม"` (`len=4`), `"ดีๆ"` (`len=3`), `"ๆฯ"` (`len=2`) | `next_cell_offset` vs `find_thai_cluster_end` | `"เกาะ"`: 4 cells `[0, 1, 2, 3, 4]`, 1 syllable `[0, 4]`; `"ธรรม"`: 4 cells, syllables `[0, 3]` (`ธรร`) + `[3, 4]` (`ม`); `"ดีๆ"`: 2 cells `[0, 2, 3]`, 1 cluster `[0, 3]`; `"ๆฯ"`: standalone `[0, 1, 2]` |
| **`test_sara_am_cell_and_syllable`** | `"น้ำ"` (`len=3`) & `"กำ"` (`len=2`) | `is_sara_am`, `is_thai_combining`, cell stops, syllable breaks | `"น้ำ"` has cell stops `[0, 2, 3]` and syllable `[0, 3]`; `"กำ"` has cell stops `[0, 1, 2]` and syllable `[0, 2]` |
| **`test_sara_am_renderer_neighbor_refresh`** | Frame 1: `"กำ"` (`x=0: 'ก'`, `x=1: 'ำ'`); Frame 2a: delete `'ำ'`; Frame 2b: change `'ก'` $\rightarrow$ `'ข'` | Call wrapped `prompt_toolkit.renderer._output_screen_diff` | In Frame 2a, `prev_row[0]` (`'ก'`) is poisoned and re-emitted; in Frame 2b, `prev_row[1]` (`'ำ'`) is poisoned and re-emitted (Lao `U+0EB3` tested identically) |
| **`test_document_jk_vertical_snap`** | `"abcdef\nที่ดิน"` | Cursor at `(row=0, col=2)`, call `get_cursor_down_position(1)` | Lands at `(row=1, col=0)` (`ท`), **not** `(row=1, col=2)` (`◌่`) |
| **`test_vi_x_X_s_r_tilde_dollar_via_key_processor`** | `"ที่ดิน"` in `Editor()` | Feed `'x'`, `'X'`, `'s'`, `'r'`, `'~'`, `'$'` through `editor.application.key_processor` | Confirms `pyvim/key_bindings.py` overrides `load_vi_bindings()`: `'x'` at `0` yields `"ดิน"`; `'$'` lands on `col=5` (`น`, or `col=0` on `"ที่"`); `'~'` advances 1 cell cluster (`0` $\rightarrow$ `3`) |
| **`test_formatted_text_stray_combining_cleanup`** | `FormattedTextControl([("", "ที่")])` | Render into `Screen` and run `_sanitize_and_invalidate_sara_am` | `screen.data_buffer[0][0].char == "ที่"`, `screen.data_buffer[0][1].char == " "` (stray `'่'` cleared) |

### 5.1 Implementation Record & Refinements Beyond Initial Draft (2026-11-06)

* **Implemented Modules**: [`pyvim/thai.py`](../pyvim/thai.py)[^src-thai], [`pyvim/key_bindings.py`](../pyvim/key_bindings.py)[^src-key-bindings], [`pyvim/editor.py`](../pyvim/editor.py)[^src-editor], and [`tests/test_thai.py`](../tests/test_thai.py)[^src-test-thai] (13 unit tests in `tests/test_thai.py`, 68 total passing; verified with `mypy --python-version 3.10` and `ast.parse(..., feature_version=(3, 10))`).
* **Refinements Discovered During Implementation**:
  1. **`KeyProcessor._fix_vi_cursor_position` Cell-Cluster Clamp**: `prompt_toolkit`'s `KeyProcessor._call_handler` invokes `_fix_vi_cursor_position` after every Vi command, which previously executed `buff.cursor_position -= 1` whenever the cursor reached EOL in Navigation mode — parking the cursor on a trailing combining mark (e.g. `◌่` at `col=6` of `"ผู้ใหญ่"`). `install_prompt_toolkit_thai_patches()` wraps `_fix_vi_cursor_position` to clamp to `prev_cell_offset(line, len(line), 1)` at EOL and `snap_to_cell_start(line, col)` mid-line.
  2. **`Document.find_start_of_previous_word` & `find_boundaries_of_current_word` + Normal-Mode `e`/`E`**: In `prompt_toolkit/key_binding/bindings/vi.py`, `b`/`B` call `Document.find_start_of_previous_word` (rather than `find_previous_word_beginning`), `iw`/`aw`/`*`/`#` call `Document.find_boundaries_of_current_word`, and `e`/`E` compute `end - 1` (which would land on a trailing combining mark in Normal mode when a word ends with `base + comb*`). Wrapping `find_start_of_previous_word` and `find_boundaries_of_current_word` and binding Normal-mode `e`/`E` (`~vi_waiting_for_text_object_mode`) to `prev_cell_offset(doc.text, pos + end, 1)` keeps both Normal-mode `e` and operator-pending `de`/`ce`/`ye` cell-cluster-safe.
  3. **`_sanitize_and_invalidate_sara_am` Row Width Bound**: Used `max(max(new_row.keys(), default=0), max(prev_row.keys(), default=0)) + 1` (clamped to `width`) so deleting `SARA AM` at the end of a row still inspects the column that previously held `SARA AM`.

---

## References

[^src-setup]: `setup.py` (`install_requires` specifying `prompt_toolkit>=2.0.0,<3.1.0`) — [../setup.py](../setup.py)
[^src-thai]: `pyvim/thai.py` (Thai & Lao cell-cluster scanners, two-tier word breaking, SARA AM renderer pre-pass, version-gated `prompt_toolkit` patch installer) — [../pyvim/thai.py](../pyvim/thai.py)
[^src-editor]: `pyvim/editor.py` (`Editor._create_application`, `Editor.__init__`) — [../pyvim/editor.py](../pyvim/editor.py)
[^src-key-bindings]: `pyvim/key_bindings.py` (`create_key_bindings`) — [../pyvim/key_bindings.py](../pyvim/key_bindings.py)
[^src-layout]: `pyvim/layout.py` (`EditorLayout`, `WindowStatusBarRuler`) — [../pyvim/layout.py](../pyvim/layout.py)
[^src-bench]: `tools/bench_plans.py` (Reproducible cell-cluster & latency benchmark script) — [../tools/bench_plans.py](../tools/bench_plans.py)
[^src-test-thai]: `tests/test_thai.py` (Unit test suite for Thai & Lao support) — [../tests/test_thai.py](../tests/test_thai.py)
