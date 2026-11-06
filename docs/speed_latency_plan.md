---
type: project_priority
title: "Speed, Latency & Python 3.15 Stability Plan for pyvim"
description: "Codebase audit, reproducible benchmarks (tools/bench_plans.py), and actionable optimization plan to fix Python 3.14+ startup crashes and reduce latency in pyvim without modifying prompt-toolkit."
status: draft
sources:
  - ../pyvim/editor.py
  - ../pyvim/editor_buffer.py
  - ../pyvim/window_arrangement.py
  - ../pyvim/layout.py
  - ../pyvim/lexer.py
  - ../pyvim/reporting.py
  - ../pyvim/completion.py
  - ../pyvim/style.py
  - ../pyvim/commands/commands.py
  - ../pyvim/io/backends.py
  - ../tools/bench_plans.py
verified: machine-confirmed
stale_after: 2027-01-01T00:00:00Z
tags: [performance, latency, optimization, python-3.15, asyncio, lexer, rendering]
generated:
  by: "Antigravity (Gemini 4 Argon)"
  at: "2026-11-05T18:05:00Z"
timestamp: 2026-11-05T18:05:00Z
---

# Speed, Latency & Python 3.15 Stability Plan for `pyvim`

This document catalogs the stability bugs, per-keystroke latency bottlenecks, and startup/rendering overhead identified across the `pyvim` codebase. Every optimization in this plan is designed to be implemented **purely inside `pyvim`** without modifying `prompt_toolkit`, and all benchmark figures are reproducible via `python tools/bench_plans.py`[^src-bench].

---

## 1. Executive Summary, Reproducible Benchmarks & Execution Order

### 1.1 Priority Matrix

| Rank | Subsystem | Location | Current Issue & Measured Cost | Target After Fix |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | **Python 3.14+ `asyncio` Startup Crash & Reporter Lockup** | `pyvim/editor_buffer.py:174-217`, `pyvim/window_arrangement.py:403`[^src-editor-buffer][^src-window-arrangement] | Opening any file before `Editor.run()` crashes on Python 3.14+ (`get_event_loop()` raises `RuntimeError` when no loop is running); unnamed buffers permanently lock `_reporter_is_running = True`; non-Python files spawn background executor tasks + extra full-screen redraws on every keystroke. | **0 crashes**, **0 background tasks** for non-`.py` files, debounced `pyflakes` checks. |
| **P1** | **Per-Keystroke `DocumentLexer` Re-instantiation & Eager EOF Lexing** | `pyvim/lexer.py:19-31`[^src-lexer] | Rebuilds `PygmentsLexer.from_filename()` on every edit and hits `prompt_toolkit`'s eager `list(get_text_fragments())` (`pygments.py:264`), which lexes from `start_lineno` all the way to EOF (`129.51 ms` at top of a 4,000-line `.py` file; `66.07 ms` at line 2,000). | **`1.41 ms`** at top (**~92x faster**), **`3.13 ms`** at line 2,000 (**~21x faster**). |
| **P2** | **Eager Compilation of All 50 Pygments Colorschemes** | `pyvim/style.py:33-37`, `pyvim/editor.py:80`[^src-style][^src-editor] | `Editor.__init__` calls `generate_built_in_styles()`, importing and compiling all 50 Pygments styles (`22.43 ms` on macOS arm64; `~60 ms` on Linux VMs) even though only `'vim'` is active and `editor.styles` is only used for `:colorscheme` tab-completion names. | **`0.10 ms`** at startup (**>200x faster**). |
| **P3** | **Singleton & Line-Cached `DocumentWordsCompleter`** | `pyvim/completion.py:12-55`[^src-completion] | `DocumentCompleter` instantiates a fresh `DocumentWordsCompleter()` on every call, and `DocumentWordsCompleter` runs `re.split(r'\W', document.text)` over the entire buffer (`3.11 ms` on 4,000 lines). | **`0.15 ms`** per keystroke (**~20x faster**) via persistent completer instance + cached non-cursor line words + `bisect`. |
| **P4** | **Per-Frame `ReportingProcessor` & `ReportMessageToolbar` Error Scan** | `pyvim/layout.py:278-288, 637-643`[^src-layout] | Scans `editor_buffer.report_errors` linearly (`O(V \times E)`) on every visible line per frame and calls `explode_text_fragments` inside the inner loop. | **`O(1)` dict lookup** per visible line via `report_errors_by_line`. |
| **P5** | **`codecs.open` Deprecation (Python 3.14+) & Minor Render/Dirty Cleanups** | `pyvim/io/backends.py:33-57`, `pyvim/editor_buffer.py:74-78`, `pyvim/commands/commands.py:747-750`[^src-backends][^src-commands] | `codecs.open` is officially deprecated in Python 3.14+; `:s` (`substitute`) constructs `Document(new_text)` twice per matched line; `has_unsaved_changes` compares full strings per frame (`~2.4 µs` per 100 KB). | C-accelerated `io.open`, single `Document` construction in `:s`, `O(1)` dirty flag. |

### 1.2 Reproducible Benchmark Output (`python tools/bench_plans.py`)

```text
Python 3.15.2 (arm64), prompt_toolkit 3.0.53

=== 2. Speed & Latency Plan Micro-Benchmarks ===
  P1a DocumentLexer (top 40 lines of 4000-line file): current=129.51 ms -> cached+streaming=1.41 ms
  P1b DocumentLexer (middle 40 lines @ 2000 of 4000-line file): current=66.07 ms -> cached+streaming=3.13 ms
  P1c DocumentLexer (bottom 40 lines of 4000-line file): current=3.33 ms -> cached+streaming=3.18 ms
  P2 Style init (50 styles): eager=22.43 ms -> lazy('vim')=0.10 ms
  P5 DocumentWordsCompleter (4000 lines, typing on current line): fresh=3.11 ms -> singleton_cached=0.150 ms
```

### 1.3 Recommended Cross-Plan Implementation Order

1. **Step 1 — P0 (`pyvim/editor_buffer.py`, `pyvim/editor.py`)**: Fix the Python 3.14+ startup crash (`get_event_loop()`) and `_reporter_is_running` lockup first, since opening any file via CLI currently crashes on Python 3.14/3.15.
2. **Step 2 — Thai & Lao Script Support ([`thai_support_plan.md`](thai_support_plan.md))**: Land `pyvim/thai.py` (cell clusters, syllables, `SARA AM` neighbor refresh, and version-gated `prompt_toolkit` hooks) plus `tests/test_thai.py`.
3. **Step 3 — P1 & P2 (`pyvim/lexer.py`, `pyvim/style.py`)**: Land `_StreamingPygmentsLexer` caching and lazy colorscheme loading.
4. **Step 4 — P3, P4 & P5 (`pyvim/completion.py`, `pyvim/layout.py`, `pyvim/io/backends.py`, `pyvim/commands/commands.py`)**: Land the persistent line-cached word completer, `O(1)` error line index, and `io.open` replacement.

---

## 2. P0: Fix Python 3.14+ `asyncio` Startup Crash, Reporter Lockup & Unnecessary Redraws

### Root Cause (`pyvim/editor_buffer.py:174-217`, `pyvim/window_arrangement.py:403`)

In `pyvim/window_arrangement.py:403`[^src-window-arrangement], `_add_editor_buffer` calls `eb.run_reporter()` synchronously when creating a buffer. During CLI startup (`pyvim foo.py`), `Editor.load_initial_files()` runs **before** `Editor.run()` starts `prompt_toolkit`'s `asyncio` event loop[^src-editor].

Inspecting `EditorBuffer.run_reporter` (`pyvim/editor_buffer.py:174-217`)[^src-editor-buffer] reveals four bugs:

```python
    def run_reporter(self):
        if not self._reporter_is_running:
            self._reporter_is_running = True

            # Don't run when we don't have a location. (We need a location in
            # order to know the filetype.)
            if self.location is None:
                return
            ...
            loop = get_event_loop()
```

1. **Crash on Python 3.14 & 3.15**: Calling `asyncio.get_event_loop()` when no event loop is running raises `RuntimeError: There is no current event loop in thread 'MainThread'` (changed in Python 3.14).
2. **Permanent Lockout on Unnamed Buffers**: When `self.location is None` (e.g., running `pyvim` with no arguments), line 177 sets `self._reporter_is_running = True` and line 185 returns early **without resetting `self._reporter_is_running = False`**. Even after saving the buffer as `:w foo.py`, `run_reporter()` never runs again.
3. **Critical Fix Requirement on the `except RuntimeError` Path**: When deferring `run_reporter()` because no event loop is running yet, `self._reporter_is_running` **must remain `False`** (only set `self._reporter_is_running = True` *after* `asyncio.get_running_loop()` succeeds), otherwise deferring it would recreate the exact same permanent lockout!
4. **Background Thread + Full Redraw on Non-Python Files & Un-Debounced Keystrokes**:
   * `report()` (`pyvim/reporting.py:22-38`)[^src-reporting] only checks `.endswith('.py')` *inside* the executor thread, so editing `.md`, `.json`, or `.txt` files still spawns thread-pool jobs and calls `get_app().invalidate()` on every keystroke.
   * On `.py` files, `self.report_errors = []` is cleared *before* starting the background check, causing red error lines to flicker on every keystroke.

### Solution (`pyvim/editor_buffer.py`, `pyvim/editor.py`)

```python
    def run_reporter(self):
        """
        Run diagnostic reporter asynchronously in background executor.
        """
        # 1. Fast exit BEFORE touching _reporter_is_running:
        #    Skip unnamed buffers and non-Python files immediately.
        if not self.location or not self.location.endswith('.py'):
            if self.report_errors:
                self.report_errors = []
                self.report_errors_by_line = {}
            return

        # 2. Acquire the running event loop BEFORE setting _reporter_is_running.
        #    If called before Application.run() (e.g. CLI startup on Python 3.14+),
        #    leave _reporter_is_running = False so Editor.run() can trigger it.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        if self._reporter_is_running:
            self._run_reporter_again = True
            return

        self._reporter_is_running = True
        text = self.buffer.text
        location = self.location

        def in_executor():
            return report(text, location)

        def ready(f):
            self._reporter_is_running = False
            new_errors = f.result()

            if new_errors != self.report_errors:
                self.report_errors = new_errors
                by_line = {}
                for err in new_errors:
                    by_line.setdefault(err.lineno, []).append(err)
                self.report_errors_by_line = by_line
                get_app().invalidate()

            if self._run_reporter_again:
                self._run_reporter_again = False
                self.run_reporter()

        fut = loop.run_in_executor(None, in_executor)
        fut.add_done_callback(ready)
```

And in `Editor.run()` (`pyvim/editor.py:257-260`)[^src-editor], trigger `run_reporter()` inside `pre_run()` once the event loop is active:
```python
        def pre_run():
            self.application.vi_state.input_mode = InputMode.NAVIGATION
            for eb in self.window_arrangement.editor_buffers:
                eb.run_reporter()
```

---

## 3. P1: Fix Per-Keystroke `DocumentLexer` Re-Instantiation & Eager EOF Lexing

### Root Cause (`pyvim/lexer.py:19-31` & `prompt_toolkit/lexers/pygments.py:253-264`)

Two compounding issues make syntax highlighting the largest source of keystroke latency on medium-to-large files:

1. **Per-Edit Lexer Re-Instantiation (`pyvim/lexer.py:19-31`)**[^src-lexer]:
   `DocumentLexer.lex_document(document)` calls `PygmentsLexer.from_filename(location, sync_from_start=False)` on every buffer change, scanning Pygments' global lexer registry (`~0.61 ms` per call) and discarding the `PygmentsLexer` instance.
2. **Eager Lexing to EOF in `prompt_toolkit`'s `PygmentsLexer` (`prompt_toolkit/lexers/pygments.py:253-264`)**:
   Inside `PygmentsLexer.lex_document`, `create_line_generator(start_lineno)` runs:
   ```python
   def get_text_fragments() -> Iterable[tuple[str, str]]:
       text = "\n".join(document.lines[start_lineno:])[column:]
       for _, t, v in self.pygments_lexer.get_tokens_unprocessed(text):
           yield _token_cache[t], v

   yield from enumerate(split_lines(list(get_text_fragments())), start_lineno)
   ```
   Because `get_text_fragments()` is wrapped in `list(...)` before being passed to `split_lines(...)` (which itself accepts any lazy `Iterable`), `PygmentsLexer` eagerly tokenizes **every line from `start_lineno` all the way to the end of the file** before yielding a single visible line!
   * When editing near the **top** of a 4,000-line Python file (`start_lineno = 0`), `list(get_text_fragments())` lexes all 4,000 lines on every keystroke (**`129.51 ms`**).
   * When editing near the **middle** (`line 2,000` of 4,000, `start_lineno = 1950`), it lexes 2,050 lines on every keystroke (**`66.07 ms`**).

### Solution (`pyvim/lexer.py`)

Subclass `PygmentsLexer` inside `pyvim/lexer.py` (`_StreamingPygmentsLexer`) so `create_line_generator` feeds 100-line chunks lazily into `split_lines(get_text_fragments())` without `list(...)`, and cache the lexer instance on `DocumentLexer` per `(location, document.text[:100])`[^src-bench]:

* **Top of 4,000-line `.py` file**: `129.51 ms` $\rightarrow$ **`1.41 ms` (~92x faster)**
* **Middle (line 2,000) of 4,000-line `.py` file**: `66.07 ms` $\rightarrow$ **`3.13 ms` (~21x faster)**
* **Bottom of 4,000-line `.py` file**: `3.33 ms` $\rightarrow$ **`3.18 ms`**

---

## 4. P2: Lazy-Load Built-In Pygments Styles

### Root Cause (`pyvim/style.py:33-37`, `pyvim/editor.py:80-81`)

In `pyvim/editor.py:80-81`[^src-editor]:
```python
self.styles = generate_built_in_styles()
self.current_style = get_editor_style_by_name('vim')
```
`generate_built_in_styles()` eagerly imports and compiles all **50** Pygments styles into `Style` objects on startup (`22.43 ms` on macOS arm64; `~60.5 ms` on Linux VMs), even though `self.styles` is only ever used as a list of style names for `:colorscheme` tab completion (`pyvim/commands/completer.py:67`: `WordCompleter(list(editor.styles.keys()))`).

### Solution (`pyvim/style.py`)

Populate `self.styles = {name: None for name in pygments.styles.get_all_styles()}` (or a `LazyStyleDict`) so `editor.styles.keys()` returns all 50 scheme names in **`0.10 ms`** while only compiling the active `'vim'` style on startup[^src-bench].

---

## 5. P3: Singleton & Line-Cached `DocumentWordsCompleter`

### Root Cause (`pyvim/completion.py:12-55`)

In `pyvim/completion.py`[^src-completion]:
1. `DocumentCompleter.get_completions` (line 30) instantiates a brand-new `DocumentWordsCompleter()` on every single completion invocation, so any instance-level cache on `DocumentWordsCompleter` would never hit unless the completer instance is persisted.
2. `DocumentWordsCompleter.get_completions` runs `re.split(r'\W', document.text)` across the entire file on every keystroke (`3.11 ms` on a 4,000-line file).

### Solution (`pyvim/completion.py`)

1. Instantiate `self._words_completer = DocumentWordsCompleter()` **once** inside `DocumentCompleter.__init__`.
2. Inside `DocumentWordsCompleter`, cache the sorted unique words from all **non-cursor lines** keyed by `(len(doc_lines), cursor_row, prefix_text, suffix_text)`. While the user is typing on the current line `cursor_row`, `prefix_text` and `suffix_text` are unchanged, so each keystroke only regex-scans `doc_lines[cursor_row]` (1 line) and binary-searches (`bisect.bisect_left`) the pre-sorted `_other_words_sorted` list:
   * **Measured cost (`tools/bench_plans.py`)**: Drops per-keystroke completion latency on a 4,000-line file from **`3.11 ms` to `0.150 ms` (~20x faster)**[^src-bench].

---

## 6. P4: `O(1)` Line Index for `ReportingProcessor` & `ReportMessageToolbar`

### Root Cause (`pyvim/layout.py:278-288, 637-643`)

In `pyvim/layout.py`[^src-layout]:
* `ReportingProcessor.apply_transformation` (lines 278-288) loops over `for error in self.editor_buffer.report_errors:` on every visible line of every render frame, and calls `fragments = explode_text_fragments(fragments)` inside the `if error.lineno == ti.lineno:` branch (potentially exploding the line multiple times if a line has multiple errors).
* `ReportMessageToolbar.get_tokens` (lines 637-643) also scans `report_errors` linearly on every frame.
* *(Note: `pyvim/reporting.py`'s `translate_row_col_to_index` is already `O(1)` via `Document._line_start_indexes` and only scans `O(word_len)` characters per error in the background executor, so `reporting.py` does not need index changes.)*

### Solution (`pyvim/layout.py`, `pyvim/editor_buffer.py`)

Maintain `self.report_errors_by_line: dict[int, list[ReporterError]]` on `EditorBuffer` (populated once when `ready(f)` receives new errors from the background thread):

```python
class ReportingProcessor(Processor):
    def apply_transformation(self, ti):
        errors = self.editor_buffer.report_errors_by_line.get(ti.lineno)
        if not errors:
            return Transformation(ti.fragments)

        fragments = explode_text_fragments(ti.fragments)
        for error in errors:
            for i in range(error.start_column, min(error.end_column, len(fragments))):
                style, char = fragments[i]
                fragments[i] = (style + ' class:flakerror ', char)
        return Transformation(fragments)
```

---

## 7. P5: `codecs.open` Deprecation (Python 3.14+) & Minor Render/Command Cleanups

1. **Replace Deprecated `codecs.open` with `io.open` (`pyvim/io/backends.py:33-57`)**[^src-backends]:
   Python 3.14 officially deprecated `codecs.open()` ("use `open()` instead of `codecs.open()`"). Replacing `codecs.open(path, ...)` with built-in `io.open(path, ...)` removes the deprecation hazard and uses CPython's C-buffered `BufferedReader`/`TextIOWrapper`.
2. **Avoid Double `Document(new_text)` Construction in `:s` (`pyvim/commands/commands.py:747-750`)**[^src-commands]:
   In `substitute()`, each matching line in `:s` constructs `Document(new_text)` twice (once to compute `translate_row_col_to_index(i, 0)`, then again with `cursor_position`). Computing the cursor index from the single `Document(new_text)` cuts `Document` allocations during `:%s` in half. *(Note: Python's `re` module already caches compiled regexes in `re._cache`, so `re.sub` compilation itself is already cached.)*
3. **Cache `has_unsaved_changes` Boolean (`pyvim/editor_buffer.py:74-78`)**[^src-editor-buffer]:
   While CPython's equal-length `str != str` is fast (`~2.4 µs` for 100 KB), `has_unsaved_changes` is queried multiple times per frame in `WindowStatusBar` and tab titles. Updating a `self._has_unsaved_changes` flag on `on_text_changed`, `write()`, and `reload()` makes per-frame checks strictly `O(1)`.

---

## References

[^src-editor]: `pyvim/editor.py` (`Editor.__init__`, `Editor.run`) — [../pyvim/editor.py](../pyvim/editor.py)
[^src-editor-buffer]: `pyvim/editor_buffer.py` (`EditorBuffer.has_unsaved_changes`, `EditorBuffer.run_reporter`) — [../pyvim/editor_buffer.py](../pyvim/editor_buffer.py)
[^src-window-arrangement]: `pyvim/window_arrangement.py` (`WindowArrangement._add_editor_buffer`) — [../pyvim/window_arrangement.py](../pyvim/window_arrangement.py)
[^src-layout]: `pyvim/layout.py` (`ReportingProcessor`, `ReportMessageToolbar`, `EditorLayout`) — [../pyvim/layout.py](../pyvim/layout.py)
[^src-lexer]: `pyvim/lexer.py` (`DocumentLexer.lex_document`) — [../pyvim/lexer.py](../pyvim/lexer.py)
[^src-reporting]: `pyvim/reporting.py` (`report`) — [../pyvim/reporting.py](../pyvim/reporting.py)
[^src-completion]: `pyvim/completion.py` (`DocumentCompleter`, `DocumentWordsCompleter`) — [../pyvim/completion.py](../pyvim/completion.py)
[^src-style]: `pyvim/style.py` (`generate_built_in_styles`, `get_editor_style_by_name`) — [../pyvim/style.py](../pyvim/style.py)
[^src-commands]: `pyvim/commands/commands.py` (`substitute`) — [../pyvim/commands/commands.py](../pyvim/commands/commands.py)
[^src-backends]: `pyvim/io/backends.py` (`FileIo`, `GZipFileIo`) — [../pyvim/io/backends.py](../pyvim/io/backends.py)
[^src-bench]: `tools/bench_plans.py` (Reproducible cell-cluster & latency benchmark script) — [../tools/bench_plans.py](../tools/bench_plans.py)
