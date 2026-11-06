---
type: architecture_guideline
title: "Thai & Lao Script Support Plan for pyvim"
description: "Detailed root-cause analysis, cell-cluster architecture (adapted from szn), Sara Am differential rendering refresh, version-gated prompt_toolkit integration, and test matrix for Thai/Lao in pyvim."
status: draft
sources:
  - ../setup.py
  - ../pyvim/editor.py
  - ../pyvim/editor_buffer.py
  - ../pyvim/key_bindings.py
  - ../pyvim/layout.py
  - ../tools/bench_plans.py
verified: machine-confirmed
stale_after: 2027-01-01T00:00:00Z
tags: [thai, lao, unicode, sara-am, cursor-movement, vi-mode, prompt-toolkit, szn]
generated:
  by: "Antigravity (Gemini 4 Argon)"
  at: "2026-11-05T18:05:00Z"
timestamp: 2026-11-05T18:05:00Z
---

# Thai & Lao Script Support Plan for `pyvim`

This document specifies the root causes of broken Thai/Lao cursor navigation, editing, and terminal rendering in `pyvim`, and details how to adapt the cell-cluster and renderer architecture from `szn` (`src/thai.zig`, `src/grid.zig`, `src/mode_copy.zig`, `src/server/render.zig`) into `pyvim` with `O(1)` per-keypress overhead[^src-key-bindings][^src-layout][^src-bench].

---

## 1. Problem Statement & Granularity Model: Cell Clusters vs. Syllables

In Thai (`U+0E00..U+0E7F`) and Lao (`U+0E80..U+0EFF`) scripts, there are **two distinct structural units** that a terminal Vi editor must distinguish:

1. **Terminal Cell Cluster (`base + comb*`)**:
   A single visual character column on the terminal grid consists of one **spacing base character** (`width == 1`) followed by **0 to 2 zero-width combining marks** (`GC=Mn`, `width == 0`: upper/lower vowels, tone marks, cancellation marks).
   * Leading vowels (`เ`, `แ`, `โ`, `ใ`, `ไ`), following vowels (`ะ`, `า`, `ำ`, `ๅ`), standalone symbols (`ๆ`, `ฯ`), and base consonants (`ก`–`ฮ`) are all `GC=Lo` spacing characters (`width == 1`) that occupy their own terminal cell.
2. **Orthographic Syllable / Word (`[leading_vowel] + consonant + [comb*] + [following_vowel + comb*]*` or dictionary word)**:
   A Thai syllable or word frequently spans **multiple terminal cells** (e.g., `"เกาะ"` spans 4 cells; `"น้ำ"` spans 2 cells; `"ผู้ใหญ่"` spans 4 cells across 2 syllables).

### 1.1 Which Vi Motions & Operators Use Which Unit?

Following `szn`'s copy-mode design (`src/mode_copy.zig`), character-wise motions/edits operate on **Cell Clusters**, whereas word-wise motions/text-objects operate on **Syllable / Word Boundaries**:

| Granularity Unit | Vi Motions & Operators | Behavior on Thai Text |
| :--- | :--- | :--- |
| **Cell Cluster (`base + comb*`)** | `h`, `l`, `<Left>`, `<Right>`, `<Space>`, `<Backspace>`, `0`, `^`, `$`, `j`, `k`, `<Esc>`, `a`, `x`, `X`, `s`, `r<char>`, `~`, `dh`, `dl`, `ch`, `cl`, `yh`, `yl` | Steps or mutates **1 visual terminal cell** at a time. Never parks the cursor on a zero-width combining mark (`GC=Mn`) and never slices a cell cluster in half. |
| **Syllable / Word (`find_thai_word_breaks`)** | `w`, `b`, `e`, `W`, `B`, `E`, `dw`, `cw`, `yw`, `diw`, `ciw`, `yiw`, `daw`, `caw`, `yaw`, `*`, `#` | Steps or operates across **1 Thai word** (Tier 1: `libthai` `th_brk_wc` dictionary segmentation) or **1 orthographic syllable** (Tier 2 fallback: `find_thai_cluster_end`). |

### 1.2 Concrete Walkthroughs Across Canonical Thai Cases

All cell starts (`cell_starts`) and full stop lists including EOL (`stops_with_eol`) below are verified by `tools/bench_plans.py`[^src-bench]:

| Sample Word | Codepoints (`len`) | Visual Cells (`wcswidth`) | `cell_starts` (Normal-mode valid cursor cols) | `stops_with_eol` (`h`/`l` step offsets + EOL) | Syllable / Word Boundaries (`w`/`b`/`e`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`"ที่ดิน"`** ("land") | `6` (`ท`, `◌ี`, `◌่`, `ด`, `◌ิ`, `น`) | `3` (`ที่` \| `ดิ` \| `น`) | `[0, 3, 5]` | `[0, 3, 5, 6]` (3 steps) | Tier 1 (`libthai`): `[0, 6]` (1 word) or `[0, 3, 6]`; Tier 2: `[0, 3, 5, 6]` |
| **`"ผู้ใหญ่"`** ("adult") | `7` (`ผ`, `◌ู`, `◌้`, `ใ`, `ห`, `ญ`, `◌่`) | `4` (`ผู้` \| `ใ` \| `ห` \| `ญ่`) | `[0, 3, 4, 5]` | `[0, 3, 4, 5, 7]` (4 steps) | Tier 1 (`libthai`): `[0, 7]`; Tier 2: `[0, 3, 5, 7]` (`ผู้` \| `ให` \| `ญ่`) |
| **`"เกาะ"`** ("island") | `4` (`เ`, `ก`, `า`, `ะ`) | `4` (`เ` \| `ก` \| `า` \| `ะ`) | `[0, 1, 2, 3]` | `[0, 1, 2, 3, 4]` (**4 cell steps** for `h`/`l`) | Tier 1 & Tier 2: **`[0, 4]` (1 syllable step** for `w`/`b`/`e`) |
| **`"น้ำ"`** ("water", Sara Am) | `3` (`น`, `◌้`, `ำ`) | `2` (`น้` \| `ำ`) | `[0, 2]` | `[0, 2, 3]` (2 cell steps: `น้` then `ำ`) | Tier 1 & Tier 2: **`[0, 3]` (1 syllable step** for `w`/`b`/`e`) |
| **`"กำ"`** ("hold", Sara Am) | `2` (`ก`, `ำ`) | `2` (`ก` \| `ำ`) | `[0, 1]` | `[0, 1, 2]` (2 cell steps: `ก` then `ำ`) | Tier 1 & Tier 2: **`[0, 2]` (1 syllable step** for `w`/`b`/`e`) |
| **`"ๆฯ"`** (symbols) | `2` (`ๆ` `U+0E46`, `ฯ` `U+0E2F`) | `2` (`ๆ` \| `ฯ`) | `[0, 1]` | `[0, 1, 2]` (2 cell steps) | Tier 1 & Tier 2: `[0, 1, 2]` (standalone tokens) |

### 1.3 Special Case: Thai/Lao SARA AM (`U+0E33` `ำ` / `U+0EB3` `ຳ`)

`SARA AM` (`U+0E33` Thai `ำ`, `U+0EB3` Lao `ຳ`) requires explicit attention across both the cell model and the terminal diff renderer (a key lesson from `szn` commit `71ba808` / `szn/src/server/render.zig:664-694`):

1. **Unicode Category & Cell Width**:
   * `U+0E33` and `U+0EB3` have General Category `Lo` (Letter, Other), **not** `Mn` (Mark, Nonspacing). Thus `is_thai_combining(0x0E33)` is `False`, `is_sara_am(0x0E33)` is `True`, and `is_thai_following_vowel(0x0E33)` is `True`.
   * Both Python's `wcwidth.wcwidth('\u0e33')` and `prompt_toolkit.utils.get_cwidth('\u0e33')` return **`1`** (matching `szn/src/char_width.zig:248-250`, Unicode East Asian Width Neutral, and Alacritty).
   * Consequently, in `"น้ำ"` (`น` + `◌้` + `ำ`), Cell 0 (`x = 0`) holds `"น้"` (`[0:2]`) and Cell 1 (`x = 1`) holds `"ำ"` (`[2:3]`).
2. **Cross-Cell Nikhahit Shaping & Differential Rendering Bug**:
   * Visually, `ำ` (`U+0E33`) is rendered by terminal font shapers (e.g., Kitty, WezTerm, Ghostty with Thai fonts such as Tlwg Typo) by projecting its leading NIKKAHIT circle (`◌ํ`) **leftward onto the preceding cell `x - 1`** while drawing the `า` stem in cell `x`.
   * `prompt_toolkit.renderer._output_screen_diff` (`prompt_toolkit/renderer.py:196-225`) only emits cells where `new_char.char != old_char.char or new_char.style != old_char.style`.
   * **Bug A (Deleting/Modifying `ำ` at `x`)**: When `ำ` at column `x` is deleted (e.g., pressing `x` on `ำ` in `"กํา"`), `new_row[x - 1]` (`'ก'`) is unchanged in `Screen.data_buffer`, so `prompt_toolkit` only redraws column `x`. The terminal clears the shaped ligature across `x - 1..x`, leaving the preceding consonant at `x - 1` blank on screen!
   * **Bug B (Modifying Preceding Consonant at `x - 1`)**: When the consonant at `x - 1` changes (e.g., `rข` changing `'ก'` to `'ข'` before `'ำ'`), `new_row[x]` (`'ำ'`) is unchanged in `Screen.data_buffer`, so `prompt_toolkit` only redraws `x - 1`. Because `'ำ'` at `x` is not re-emitted, the terminal fails to project the NIKKAHIT circle onto the new consonant `'ข'`!
   * **Fix (Phase 4)**: Port `szn/src/server/render.zig:664-694` directly into a renderer pre-pass before `_output_screen_diff` so that whenever column `x` (`x >= 1`) in either the previous or current screen frame contains `SARA AM` (`U+0E33`/`U+0EB3`), a change at `x` invalidates `previous_row[x - 1]` and a change at `x - 1` invalidates `previous_row[x]`.

---

## 2. Root-Cause Audit: `prompt_toolkit` vs. `pyvim`

`pyvim` delegates its text buffer (`Document`, `Buffer`), Vi keybindings (`load_vi_bindings`), screen layout (`BufferControl`, `Window`), and differential terminal output (`_output_screen_diff`) to `prompt_toolkit` (`3.0.53` in the target environment, constrained to `>=2.0.0,<3.1.0` in `setup.py:20`[^src-setup])[^src-editor].

| Layer | File & Line (`prompt_toolkit 3.0.53`) | Current Implementation | Exact Failure Mode on Thai/Lao |
| :--- | :--- | :--- | :--- |
| **1. Cursor Left / Right** | `prompt_toolkit/document.py:695-711` | `get_cursor_left_position` returns `-min(self.cursor_position_col, count)`; `get_cursor_right_position` returns `min(count, len(self.current_line_after_cursor))`. | Moves by `±1` **codepoint** instead of `±1` **cell cluster**. Pressing `l` on `"ที่ดิน"` takes 6 presses instead of 3 and parks the cursor on zero-width marks `◌ี` (`idx=1`), `◌่` (`idx=2`), `◌ิ` (`idx=4`). |
| **2. Cursor Up / Down (`j` / `k`)** | `prompt_toolkit/document.py:713-754` | `get_cursor_up_position` / `get_cursor_down_position` call `translate_row_col_to_index(target_row, column)` using raw codepoint `column`. | Moving `j`/`k` from `col=2` on an ASCII line onto `"ที่ดิน"` lands at codepoint index `2` (`◌่`, inside Cell 0 `"ที่"`). |
| **3. Vi `x`, `X`, `s`, `r`, `~`, `$`** | `prompt_toolkit/key_binding/bindings/vi.py:626-662, 922-960, 1018-1028, 1244-1249` | `x` (`_cut_char`) deletes `min(event.arg, len(current_line_after_cursor))` codepoints; `s` deletes 1 codepoint; `r` deletes `event.arg` codepoints; `~` (`_reverse_case`) overwrites `1` codepoint (`current_char`); `$` moves to `len(line)`. | Pressing `x` on `"ที่"` deletes only `ท` (`U+0E17`), orphaning `◌ี` and `◌่` so they attach to the preceding character or render as dotted circles. Pressing `~` on `"ที่"` advances `cursor_position` by `1` onto `◌ี`. |
| **4. Vi Word Regex (`w`/`b`/`e`)** | `prompt_toolkit/document.py:34-43` | `_FIND_WORD_RE = re.compile(r"([a-zA-Z0-9_]+|[^a-zA-Z0-9_\s]+)\s*")` | In Python 3 `re` (Unicode mode), `\w` is unnecessary here because `_FIND_WORD_RE` hardcodes ASCII `[a-zA-Z0-9_]+`! Every Thai character matches `[^a-zA-Z0-9_\s]+`, so an entire unspaced Thai sentence is treated as **one giant punctuation token**. |
| **5. Screen Copy & Diff Renderer** | `prompt_toolkit/layout/containers.py:2046-2082`, `prompt_toolkit/renderer.py:196-225` | `Window._copy_body` writes `new_buffer_row[x + xpos] = char` before merging `char_width == 0` into `x + xpos - pw`; `_output_screen_diff` diffs cells independently without checking `SARA AM` (`U+0E33`/`U+0EB3`). | For `BufferControl`, `get_line()` (`controls.py:785`) appends `" "`, which overwrites the stray mark at EOL and keeps `rowcol_to_yx` / `yx_to_rowcol` aligned on cell starts. However, `FormattedTextControl` (status/tab bars) and soft-wrapped lines retain a stray `width == 0` mark at `x + xpos`, and `_output_screen_diff` fails to refresh the neighbor cell when `SARA AM` or its preceding consonant changes. |

---

## 3. Architecture Adapted from `szn` & Reproducible Performance

### 3.1 Porting `szn/src/thai.zig` to `pyvim/thai.py`

We create a dedicated, zero-dependency module `pyvim/thai.py` ported from `szn/src/thai.zig`:

```python
from __future__ import annotations

import ctypes
import ctypes.util
import threading

# Exact GC=Mn combining codepoints for Thai (U+0E31..U+0E4E) and Lao (U+0EB1..U+0ECD).
# Note: SARA AM (U+0E33 / U+0EB3) is GC=Lo (spacing following vowel, width 1), NOT Mn.
_THAI_COMBINING_CPS: frozenset[int] = frozenset({
    # Thai combining marks
    0x0E31,                                     # MAI HAN-AKAT
    0x0E34, 0x0E35, 0x0E36, 0x0E37,             # SARA I, II, UE, UEE
    0x0E38, 0x0E39, 0x0E3A,                     # SARA U, UU, PHINTHU
    0x0E47,                                     # MAITAIKHU
    0x0E48, 0x0E49, 0x0E4A, 0x0E4B,             # MAI EK, THO, TRI, CHATTAWA
    0x0E4C, 0x0E4D, 0x0E4E,                     # THANTHAKHAT, NIKHAHIT, YAMAKKAN
    # Lao combining marks
    0x0EB1,                                     # MAI KAN
    0x0EB4, 0x0EB5, 0x0EB6, 0x0EB7,             # VOWEL I, II, Y, YY
    0x0EB8, 0x0EB9, 0x0EBB, 0x0EBC,             # VOWEL U, UU, MAI KON, LO
    0x0EC8, 0x0EC9, 0x0ECA, 0x0ECB,             # TONE MAI EK, DO, TI, CATAWA
    0x0ECC, 0x0ECD,                             # CANCELLATION MARK, NIGGAHITA
})


def is_thai_combining(cp: int) -> bool:
    """True if cp is a zero-width Thai or Lao combining mark (GC=Mn)."""
    return cp in _THAI_COMBINING_CPS


def is_sara_am(cp: int) -> bool:
    """True if cp is Thai SARA AM (U+0E33) or Lao SARA AM (U+0EB3)."""
    return cp == 0x0E33 or cp == 0x0EB3


def is_thai_leading_vowel(cp: int) -> bool:
    """True if cp is a visual-order leading vowel (U+0E40..U+0E44, U+0EC0..U+0EC4)."""
    return (0x0E40 <= cp <= 0x0E44) or (0x0EC0 <= cp <= 0x0EC4)


def is_thai_following_vowel(cp: int) -> bool:
    """True if cp is a spacing following vowel (ะ, า, ำ, ๅ) or MAI HAN-AKAT."""
    return cp in (
        0x0E30, 0x0E31, 0x0E32, 0x0E33, 0x0E45,
        0x0EB0, 0x0EB1, 0x0EB2, 0x0EB3,
    )


def is_thai_base(cp: int) -> bool:
    """True if cp is a Thai/Lao base consonant."""
    if (0x0E01 <= cp <= 0x0E2E) or (0x0E81 <= cp <= 0x0EAE):
        return True
    return cp in (0x0EDC, 0x0EDD, 0x0EDE, 0x0EDF)


def is_thai_script(cp: int) -> bool:
    """True if cp is in the Thai (U+0E00..U+0E7F) or Lao (U+0E80..U+0EFF) blocks."""
    return 0x0E00 <= cp <= 0x0EFF
```

### 3.2 `O(1)` Local Cell-Cluster Boundary Scanners

```python
def snap_to_cell_start(line: str, col: int) -> int:
    """
    If `col` is parked on a Thai/Lao combining mark inside `line`,
    walk backward to the base character of the cell cluster.
    """
    n = len(line)
    if col <= 0 or n == 0 or line.isascii():
        return max(0, min(col, n))
    idx = min(col, n)
    comb = _THAI_COMBINING_CPS
    while idx > 0 and idx < n and ord(line[idx]) in comb:
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
    comb = _THAI_COMBINING_CPS
    for _ in range(count):
        if idx >= n:
            break
        idx += 1
        while idx < n and ord(line[idx]) in comb:
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
    comb = _THAI_COMBINING_CPS
    # If currently mid-cluster on a combining mark, first snap to its base:
    while idx > 0 and idx < len(line) and ord(line[idx]) in comb:
        idx -= 1
    for _ in range(count):
        if idx <= 0:
            break
        idx -= 1
        while idx > 0 and ord(line[idx]) in comb:
            idx -= 1
    return idx
```

### 3.3 Two-Tier Syllable / Word Breaking (`w`, `b`, `e`)

Ported directly from `szn/src/thai.zig:215-248` and `szn/src/thai.zig:700-792`:

1. **Tier 1 (`libthai` via `ctypes`, optional runtime `dlopen`)**:
   * Probes `ctypes.util.find_library("thai")` plus explicit fallback paths (`libthai.so.0`, `libthai.so`, `/opt/homebrew/lib/libthai.dylib`, `/usr/local/lib/libthai.dylib`, `libthai.dylib`) behind a thread-safe `threading.Once`-style loader.
   * Calls `th_brk_wc(wchar_t_buf, pos_array, n)` on contiguous Thai runs (`U+0E01..U+0E7F`).
2. **Tier 2 (`find_thai_cluster_end` TCC-lite heuristic fallback)**:
   * Matches `szn/src/thai.zig:215-248` (`[leading_vowel] + base_consonant + [combining*] + [following_vowel + combining*]*`):
     ```python
     def find_thai_cluster_end(cps: list[int], start: int) -> int:
         n = len(cps)
         if start >= n:
             return n
         i = start
         if is_thai_leading_vowel(cps[i]):
             i += 1
             if i >= n:
                 return i
         if is_thai_base(cps[i]):
             i += 1
             while i < n and is_thai_combining(cps[i]):
                 i += 1
             while i < n and is_thai_following_vowel(cps[i]):
                 i += 1
                 while i < n and is_thai_combining(cps[i]):
                     i += 1
             return i
         i += 1
         while i < n and is_thai_combining(cps[i]):
             i += 1
         return i
     ```
   * Note that the `while i < n and is_thai_following_vowel(cps[i]):` loop handles **multiple following vowels** (such as `"เกาะ"` = `เ` + `ก` + `า` + `ะ`, and `"น้ำ"` = `น` + `◌้` + `ำ`), keeping `"เกาะ"` (`[0, 4]`) and `"น้ำ"` (`[0, 3]`) intact as single syllables even when `libthai` is not installed.
   * Standalone symbols `ๆ` (`U+0E46` MAI YAMOK) and `ฯ` (`U+0E2F` PAIYANNOI) are neither leading vowels nor base consonants, so they fall through to `i += 1` (`[start, start + 1]`), acting as discrete single-character word tokens.

### 3.4 Reproducible Micro-Benchmarks (`tools/bench_plans.py`)

Running `python tools/bench_plans.py` on Python 3.15.2 (`macOS arm64`, `prompt_toolkit 3.0.53`) confirms that local cell-cluster scanning adds sub-microsecond latency[^src-bench]:

```text
=== 1. Thai Cell-Cluster Verification & Micro-Benchmarks ===
  'ที่ดิน'   len=6 cells=3 cell_starts=[0, 3, 5] stops_with_eol=[0, 3, 5, 6]
  'ผู้ใหญ่'  len=7 cells=4 cell_starts=[0, 3, 4, 5] stops_with_eol=[0, 3, 4, 5, 7]
  'เกาะ'     len=4 cells=4 cell_starts=[0, 1, 2, 3] stops_with_eol=[0, 1, 2, 3, 4]
  'น้ำ'      len=3 cells=2 cell_starts=[0, 2] stops_with_eol=[0, 2, 3]
  'กำ'       len=2 cells=2 cell_starts=[0, 1] stops_with_eol=[0, 1, 2]
  'ๆฯ'       len=2 cells=2 cell_starts=[0, 1] stops_with_eol=[0, 1, 2]
  next_cell_offset (ASCII fast-path): 51.3 ns/call
  next_cell_offset (Thai cluster):    213.4 ns/call
```

---

## 4. Detailed Implementation Plan & Version-Gated `prompt_toolkit` Integration

### 4.1 Architectural Safeguard: Version Gating & Fallbacks (`prompt_toolkit >=2.0.0,<3.1.0`)

Because `setup.py:20` declares `prompt_toolkit>=2.0.0,<3.1.0`[^src-setup], any integration that wraps `prompt_toolkit` methods must be:
1. **Scoped to explicit, minimal entry points** rather than copying large private methods (`Window._copy_body` is **not** replaced or copied; see Phase 4 below).
2. **Guarded by a version gate and signature check** (`install_prompt_toolkit_thai_patches()` in `pyvim/thai.py`, called once from `Editor.__init__` in `pyvim/editor.py`[^src-editor]):
   * Verifies `hasattr(Document, "get_cursor_left_position")`, `hasattr(Document, "get_cursor_right_position")`, `hasattr(Document, "get_cursor_up_position")`, `hasattr(Document, "get_cursor_down_position")`, and `hasattr(Renderer, "render")`.
   * Runs a startup self-check on `Document("ที่ดิน", cursor_position=0).get_cursor_right_position(1) == 3`.
   * If an incompatible `prompt_toolkit` version is encountered, logs a warning and leaves the unpatched method intact rather than raising an unhandled exception on startup.

### Phase 1: Create `pyvim/thai.py`
Implement:
1. Character classification predicates: `is_thai_combining`, `is_sara_am`, `is_thai_leading_vowel`, `is_thai_following_vowel`, `is_thai_base`, `is_thai_script`.
2. Cell-cluster boundary scanners: `snap_to_cell_start`, `next_cell_offset`, `prev_cell_offset`, `cell_cluster_len(line, col)`.
3. Two-tier word/syllable segmentation: `find_thai_cluster_end`, `find_thai_word_breaks`, and Thai-aware `find_next_word_beginning`, `find_next_word_ending`, `find_previous_word_beginning`, `find_previous_word_ending`, `get_word_under_cursor`.

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
> However, **`x`, `X`, `s`, `r`, `~`, and `$` do NOT call `get_cursor_left/right_position`** — they slice raw codepoint counts directly in `vi.py` and therefore require explicit bindings in Phase 3.

### Phase 3: Cell-Cluster Vi Editing Bindings (`x`, `X`, `s`, `r`, `~`, `$`) & Precedence Verification

In `pyvim/key_bindings.py`[^src-key-bindings], register Thai-aware Normal-mode handlers on `editor.key_bindings`:

1. **Why `pyvim/key_bindings.py` Precedence Wins Over `prompt_toolkit`'s `load_vi_bindings()`**:
   * In `prompt_toolkit/application/application.py:1487-1503`, `_CombinedRegistry._create_key_bindings` builds `[container_bindings..., self.app.key_bindings, page_navigation_bindings, self.app._default_bindings]` and reverses it (`key_bindings[::-1]`), placing `self.app.key_bindings` (`pyvim`) **after** `self.app._default_bindings` (`load_vi_bindings`).
   * In `prompt_toolkit/key_binding/key_processor.py:189`, `KeyProcessor` dispatches `matches[-1]` (the last matching binding in the merged registry). Therefore, a binding registered on `editor.key_bindings` with `filter=vi_navigation_mode` deterministically overrides `load_vi_bindings()`'s default handler.
2. **Exact Specifications for `x`, `X`, `s`, `r`, `~`, `$`**:
   * **`x` (`delete-char-forward`)**:
     Computes `end_col = next_cell_offset(doc.current_line, doc.cursor_position_col, event.arg)`, deletes `end_col - doc.cursor_position_col` codepoints (`buffer.delete(count=span)`), and stores the deleted cluster(s) in the clipboard.
   * **`X` (`delete-char-backward`)**:
     Computes `start_col = prev_cell_offset(doc.current_line, doc.cursor_position_col, event.arg)`, deletes `doc.cursor_position_col - start_col` codepoints before the cursor (`buffer.delete_before_cursor(count=span)`), and stores the deleted cluster(s) in the clipboard.
   * **`s` (`substitute-char`)**:
     Deletes `next_cell_offset(doc.current_line, doc.cursor_position_col, event.arg) - doc.cursor_position_col` codepoints, stores them in the clipboard, and switches `vi_state.input_mode = InputMode.INSERT`.
   * **`r<char>` (`replace-char`, `filter=vi_replace_single_mode`)**:
     Replaces `event.arg` cell clusters (`span = next_cell_offset(line, col, event.arg) - col`) with `event.data * event.arg`, steps back 1 cell cluster, and returns to `InputMode.NAVIGATION`.
   * **`~` (`reverse-case`, `filter=vi_navigation_mode`)**:
     Extracts the current cell cluster `cluster = line[col : next_cell_offset(line, col, 1)]` (handling both Thai cells and precomposed/decomposed Latin+combining clusters), replaces that span with `cluster.swapcase()`, and advances `cursor_position` to `next_cell_offset` (so pressing `~` on `"ที่ดิน"` advances across `"ที่"` in 1 step instead of landing on `◌ี`).
   * **`$` in Navigation Mode (`filter=vi_navigation_mode & ~vi_waiting_for_text_object_mode`)**:
     Moves the cursor to the start of the **last cell cluster** on the current line: `prev_cell_offset(line, len(line), 1)`. Note that operator-pending `$` (`d$`, `c$`, `y$`) is left untouched (`vi_waiting_for_text_object_mode`), so `d$` continues to delete through `len(line)` including all trailing combining marks.

### Phase 4: Rendering Fix — `BufferControl` Coordinate Analysis & `SARA AM` Neighbor Refresh

#### 4.1 Why `Window._copy_body` Does Not Need Monkey-Patching for `rowcol_to_yx`
Inspecting `BufferControl.create_content` (`prompt_toolkit/layout/controls.py:785`) and `Window._copy_body` (`prompt_toolkit/layout/containers.py:2046-2082`) live against `prompt_toolkit 3.0.53` reveals:
1. `BufferControl.get_line` appends a trailing space `[("", " ")]` (`width == 1`) to every line in a `BufferControl`.
2. For `"ที่ดิน"` (`len=6`, plus trailing `" "` at `col=6`), `Window._copy_body` produces:
   * `screen.data_buffer[0]`: `{0: 'ที่', 1: 'ดิ', 2: 'น', 3: ' '}` (the trailing `' '` overwrites the temporary `new_buffer_row[x + xpos] = char` combining mark).
   * `rowcol_to_yx`: `{(0, 0): (0, 0), (0, 1): (0, 1), (0, 2): (0, 1), (0, 3): (0, 1), (0, 4): (0, 2), (0, 5): (0, 2), (0, 6): (0, 3)}`.
   * At every cell-start offset (`col = 0, 3, 5` and EOL `6`), `rowcol_to_yx[0, col]` is **already** `(0, 0)`, `(0, 1)`, `(0, 2)`, `(0, 3)`.
   * For mouse clicks (`containers.py:1828`), `yx_to_rowcol = {v: k for k, v in rowcol_to_yx.items()}` evaluates to `{(0, 0): (0, 0), (0, 1): (0, 3), (0, 2): (0, 5), (0, 3): (0, 6)}` — mapping each screen column directly to the **base consonant index** of that cell!
   * In Insert mode, after typing `ท` (`col=1`) or `ที` (`col=2`), `rowcol_to_yx` places the Insert-mode cursor at `(0, 1)` (the cell immediately after `"ที"` where the next character will be inserted).

#### 4.2 What Actually Needs Fixing in the Renderer (`Renderer.render` Pre-Pass)
Two rendering defects remain in `prompt_toolkit`:
1. **Stray Zero-Width Combining Marks in `FormattedTextControl` / Wrapped Lines**:
   Unlike `BufferControl`, `FormattedTextControl` (used by `pyvim` status bars, tab bars, and message bars) does not append `" "`, leaving `{0: 'ที่', 1: '่'}` where cell `1` has `cell.width == 0 and cell.char != ""`.
2. **`SARA AM` (`U+0E33` / `U+0EB3`) Differential Redraw Failure (`szn` `71ba808`)**:
   In `prompt_toolkit/renderer.py:196-225`, `_output_screen_diff` compares `new_row[c]` against `previous_row[c]` cell-by-cell. When `SARA AM` at column `c` is deleted/modified, `c - 1` is not re-emitted; when the consonant at `c - 1` is modified, `SARA AM` at `c` is not re-emitted.

Both are solved cleanly in a lightweight wrapper around `Renderer.render` (no private `_copy_body` override required):

```python
from prompt_toolkit.layout.screen import Char

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
        max_x = min(width, max(new_row.keys(), default=0) + 1, max(prev_row.keys(), default=0) + 1)
        for x in range(1, max_x):
            prev_cell = prev_row[x]
            cur_cell = new_row[x]
            if _cell_has_sara_am(prev_cell) or _cell_has_sara_am(cur_cell):
                prev_left = prev_row[x - 1]
                cur_left = new_row[x - 1]
                left_changed = (cur_left.char != prev_left.char) or (cur_left.style != prev_left.style)
                cur_changed = (cur_cell.char != prev_cell.char) or (cur_cell.style != prev_cell.style)
                if cur_changed and not left_changed:
                    prev_row[x - 1] = _SARA_AM_POISON
                elif left_changed and not cur_changed:
                    prev_row[x] = _SARA_AM_POISON
```

---

## 5. Verification & Unit Test Matrix (`tests/test_thai.py`)

We will add `tests/test_thai.py` covering every layer and edge case:

| Test Case | Input Text | Operation / Assertion | Expected Result |
| :--- | :--- | :--- | :--- |
| **`test_cell_offsets_thi_din`** | `"ที่ดิน"` (`len=6`, 3 cells) | `cell_starts` & `stops_with_eol` | `cell_starts == [0, 3, 5]`, `stops_with_eol == [0, 3, 5, 6]` |
| **`test_cell_offsets_phu_yai`** | `"ผู้ใหญ่"` (`len=7`, 4 cells) | `cell_starts` & `stops_with_eol` | `cell_starts == [0, 3, 4, 5]`, `stops_with_eol == [0, 3, 4, 5, 7]` |
| **`test_cell_vs_syllable_ko`** | `"เกาะ"` (`len=4`, 4 cells, 1 syllable) | `h`/`l` (`next_cell_offset`) vs `w`/`b` (`find_thai_word_breaks`) | `h`/`l` stops at `[0, 1, 2, 3, 4]` (4 cell steps); `w`/`b` treats `"เกาะ"` as 1 syllable `[0, 4]` |
| **`test_sara_am_cell_and_syllable`** | `"น้ำ"` (`len=3`) & `"กำ"` (`len=2`) | `is_sara_am`, `is_thai_combining`, cell stops, syllable breaks | `is_thai_combining(0x0E33) == False`, `is_sara_am(0x0E33) == True`; `"น้ำ"` has cell stops `[0, 2, 3]` and syllable `[0, 3]`; `"กำ"` has cell stops `[0, 1, 2]` and syllable `[0, 2]` |
| **`test_sara_am_renderer_neighbor_refresh`** | Frame 1: `"กำ"` (`x=0: 'ก'`, `x=1: 'ำ'`); Frame 2a: delete `'ำ'`; Frame 2b: change `'ก'` $\rightarrow$ `'ข'` | `_sanitize_and_invalidate_sara_am(new_screen, prev_screen, 80)` | In Frame 2a, `prev_row[0]` (`'ก'`) is poisoned so `'ก'` re-emits; in Frame 2b, `prev_row[1]` (`'ำ'`) is poisoned so `'ำ'` re-emits (Lao `U+0EB3` tested identically) |
| **`test_symbols_mai_yamok_paiyannoi`** | `"ๆฯ"` (`U+0E46`, `U+0E2F`) | `next_cell_offset` & `find_thai_word_breaks` | Cell stops `[0, 1, 2]`; word breaks `[0, 1, 2]` |
| **`test_document_jk_vertical_snap`** | `"abcdef\nที่ดิน"` | Cursor at `(row=0, col=2)`, call `get_cursor_down_position(1)` | Lands at `(row=1, col=0)` (`ท`), **not** `(row=1, col=2)` (`◌่`) |
| **`test_vi_x_X_s_r_tilde_dollar_via_key_processor`** | `"ที่ดิน"` in `Editor()` | Feed `'x'`, `'X'`, `'s'`, `'r'`, `'~'`, `'$'` through `editor.application.key_processor` | Confirms `pyvim/key_bindings.py` overrides `load_vi_bindings()`: `'x'` at `0` yields `"ดิน"`; `'$'` lands on `col=5` (`น`, or `col=0` on `"ที่"`); `'~'` advances 1 cell cluster (`0` $\rightarrow$ `3`) |
| **`test_formatted_text_stray_combining_cleanup`** | `FormattedTextControl([("", "ที่")])` | Render into `Screen` and run `_sanitize_and_invalidate_sara_am` | `screen.data_buffer[0][0].char == "ที่"`, `screen.data_buffer[0][1].char == " "` (stray `'่'` cleared) |

---

## References

[^src-setup]: `setup.py` (`install_requires` specifying `prompt_toolkit>=2.0.0,<3.1.0`) — [../setup.py](../setup.py)
[^src-editor]: `pyvim/editor.py` (`Editor._create_application`, `Editor.__init__`) — [../pyvim/editor.py](../pyvim/editor.py)
[^src-key-bindings]: `pyvim/key_bindings.py` (`create_key_bindings`) — [../pyvim/key_bindings.py](../pyvim/key_bindings.py)
[^src-layout]: `pyvim/layout.py` (`EditorLayout`, `WindowStatusBarRuler`) — [../pyvim/layout.py](../pyvim/layout.py)
[^src-bench]: `tools/bench_plans.py` (Reproducible cell-cluster & latency benchmark script) — [../tools/bench_plans.py](../tools/bench_plans.py)
