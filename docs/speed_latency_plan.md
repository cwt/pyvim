---
type: project_priority
title: "Speed, Latency & Python 3.15 Stability Plan for pyvim"
description: "Codebase audit, reproducible benchmarks (tools/bench_plans.py), and the P0-P5 optimization plan - IMPLEMENTED and machine-verified at hg rev 161 (024e7f40f812); mypy follow-up sweep at rev 162 (e8122198d2b2). No prompt-toolkit modifications."
status: stable
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
  - ../pyvim/commands/completer.py
  - ../pyvim/io/backends.py
  - ../tools/bench_plans.py
  - ../tests/test_editor_buffer.py
  - ../tests/test_lexer.py
  - ../tests/test_style.py
  - ../tests/test_completion.py
  - ../tests/test_layout.py
  - ../tests/test_io_backends.py
  - ../mypy.ini
verified: machine-confirmed
stale_after: 2027-01-01T00:00:00Z
tags: [performance, latency, optimization, python-3.15, asyncio, lexer, rendering, implemented]
originally_generated:
  by: "Antigravity (Gemini 4 Argon)"
  at: "2026-11-06T02:44:00Z"
generated:
  by: "Agnes (Sapiens AI)"
  at: "2026-11-06T07:30:00Z"
timestamp: 2026-11-06T07:30:00Z
---

# Speed, Latency & Python 3.15 Stability Plan for `pyvim`

This document catalogs the stability bugs, per-keystroke latency bottlenecks, and startup/rendering overhead identified across the `pyvim` codebase. **Status: all of P0–P5 are implemented (hg rev 161, `024e7f40f812`) and machine-verified** — 42 new unit tests across six files ([`tests/`](../tests/)[^src-tests]), 55 total passing, with final figures from `python tools/bench_plans.py`[^src-bench]. A follow-up mypy baseline & sweep landed at rev 162 (`e8122198d2b2`). See §1.3 for the full implementation record. Every optimization was implemented **purely inside `pyvim`** using public APIs without modifying `prompt_toolkit`.

---

## 1. Executive Summary, Reproducible Benchmarks & Execution Order

### 1.1 Priority Matrix

| Rank | Subsystem | Location | Current Issue & Measured Cost | Target After Fix |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | **Python 3.14+ `asyncio` Startup Crash & Reporter Lockup** | `pyvim/editor_buffer.py:174-217`, `pyvim/window_arrangement.py:403`[^src-editor-buffer][^src-window-arrangement] | Opening any file before `Editor.run()` crashes on Python 3.14+ (`get_event_loop()` raises `RuntimeError` when no loop is running); unnamed buffers permanently lock `_reporter_is_running = True`; non-Python files spawn background executor tasks + extra full-screen redraws on every keystroke. | **0 crashes**, **0 background tasks** for non-`.py` files, thread-safe `call_soon_threadsafe` UI invalidation. |
| **P1** | **Per-Keystroke `DocumentLexer` Re-instantiation & Eager EOF Lexing** | `pyvim/lexer.py:19-31`[^src-lexer] | Rebuilds `PygmentsLexer.from_filename()` on every edit and hits `prompt_toolkit`'s eager `list(get_text_fragments())` (`pygments.py:264`), which lexes from `start_lineno` all the way to EOF (`131.81 ms` at top of a 4,000-line `.py` file; `69.49 ms` at line 2,000). | **`1.54 ms`** at top (**~85x faster**), **`3.33 ms`** at line 2,000 (**~21x faster**), 100% multiline docstring parity. |
| **P2** | **Eager Compilation & Entry-Point Scan of All 50 Pygments Styles** | `pyvim/style.py:33-37`, `pyvim/editor.py:80`, `pyvim/commands/completer.py:59`[^src-style][^src-editor][^src-cmd-completer] | `Editor.__init__` calls `generate_built_in_styles()`, which calls `get_all_styles()` (scanning `importlib.metadata` plugin entry points) and compiles all 50 Pygments styles (`17.87 ms` on macOS arm64; `~57 ms` on Linux x86_64) even though `editor.styles` is only iterated during `:colorscheme <Tab>` completion. | **`0.09 ms`** at startup via `_LazyStylesDict` (deferring both `get_all_styles()` and style compilation). |
| **P3** | **Singleton & Line-Cached `DocumentWordsCompleter`** | `pyvim/completion.py:12-55`[^src-completion] | `DocumentCompleter` instantiates a fresh `DocumentWordsCompleter()` on every call, and `DocumentWordsCompleter` runs `re.split(r'\W', document.text)` over the entire buffer (`3.12 ms` on 4,000 lines). | **`0.18 ms`** per keystroke (**~17–23x faster**) via persistent completer instance + cached non-cursor line words + `bisect`. |
| **P4** | **Per-Frame `ReportingProcessor` & `ReportMessageToolbar` Error Scan** | `pyvim/layout.py:272-293, 627-645`[^src-layout] | Scans `editor_buffer.report_errors` linearly (`O(V \times E)`) on every visible line per frame and calls `explode_text_fragments` inside the inner loop. | **`O(1)` dict lookup** per visible line via `report_errors_by_line`. |
| **P5** | **`codecs.open` Deprecation (Python 3.14+) & Minor Render/Dirty Cleanups** | `pyvim/io/backends.py:33-57`, `pyvim/editor_buffer.py:74-78`, `pyvim/commands/commands.py:747-750`[^src-backends][^src-commands] | `codecs.open` is officially deprecated in Python 3.14+; `:s` (`substitute`) constructs `Document(new_text)` twice per matched line; `has_unsaved_changes` compares full strings per frame (`~2.4 µs` per 100 KB). | C-accelerated `io.open`, single `Document` construction in `:s`, `O(1)` dirty flag. |

> **All of P0–P5: implemented** in hg rev 161 (`024e7f40f812`), machine-verified (42 new unit tests + `tools/bench_plans.py` parity/perf checks); follow-up fixes recorded in §1.4, mypy baseline in §1.3 (rev 162, `e8122198d2b2`).

### 1.2 Reproducible Benchmark Output (`python tools/bench_plans.py`)

*Before* implementation (the reference figures the plan was designed against):

```text
=== 2. Speed & Latency Plan Verification & Micro-Benchmarks ===
  Verified P1 multiline docstring token parity (lines 75..140): PASS
  P1a DocumentLexer (top 40 lines of 4000-line file): current=131.81 ms -> cached+streaming=1.54 ms
  P1b DocumentLexer (middle 40 lines @ 2000 of 4000-line file): current=69.49 ms -> cached+streaming=3.33 ms
  P1c DocumentLexer (bottom 40 lines of 4000-line file): current=3.38 ms -> cached+streaming=3.32 ms
  P2 Style init (50 styles): cold_eager=17.87 ms (cold get_all_styles=1.17 ms) -> deferred _LazyStylesDict startup=0.09 ms
  P3 DocumentWordsCompleter (4000 lines, typing on current line): fresh=3.12 ms -> singleton_cached=0.182 ms
```

*After* implementation (rev 161+162, Python 3.15.2 / prompt_toolkit 3.0.53, macOS arm64): the “current” column now runs the new streaming/cached code, so both sides are fast, and the hot paths beat the original targets:

```text
  Verified P1 multiline docstring token parity (lines 75..140): PASS
  P1a DocumentLexer (top 40 lines of 4000-line file): current=1.40 ms -> cached+streaming=1.36 ms   (was 128.92 ms pre-implementation)
  P1b DocumentLexer (middle 40 lines @ 2000 of 4000-line file): current=3.07 ms -> cached+streaming=3.09 ms (was 68.56 ms pre-implementation)
  P1c DocumentLexer (bottom 40 lines of 4000-line file): current=3.08 ms -> cached+streaming=3.06 ms
  P2 Style init (50 styles): cold_eager=0.44 ms (get_all_styles deferred; measured warm in-process) -> deferred _LazyStylesDict startup=0.11-0.14 ms
  P3 DocumentWordsCompleter (4000 lines, typing on current line): fresh=2.25 ms -> singleton_cached=0.038 ms
```

### 1.3 Implementation Record (rev 161–162, 2026-11-06)

* **Implementation (rev 161, `024e7f40f812`)**: P0–P5 landed as one verified changeset — 8 modified source files plus six new test modules (42 tests): [`tests/test_editor_buffer.py`](../tests/test_editor_buffer.py) (P0/P5, 9 tests), [`tests/test_lexer.py`](../tests/test_lexer.py) (P1, 5), [`tests/test_style.py`](../tests/test_style.py) (P2, 7), [`tests/test_completion.py`](../tests/test_completion.py) (P3, 8), [`tests/test_layout.py`](../tests/test_layout.py) (P4, 7), [`tests/test_io_backends.py`](../tests/test_io_backends.py) (P5, 6).[^src-tests]
* **Mypy sweep (rev 162, `e8122198d2b2`)**: added [`mypy.ini`](../mypy.ini)[^src-mypy] (`python_version = 3.15`, `ignore_missing_imports`) and fixed the 9 pre-existing code-level errors: two `no-redef` misnamed handler defs (`pwd` → `cd` for `:cd`; `set_scroll_offset` → `set_colorcolumn` for `:colorcolumn`; registration is decorator-driven, so the renames are behavior-neutral), four unannotated module-level tables in `pyvim/commands/commands.py`, `six.with_metaclass(ABCMeta, object)` → `metaclass=ABCMeta` in `pyvim/io/base.py`, and a targeted `# type: ignore[attr-defined]` on the legacy PTK2-only `prompt_toolkit.eventloop` import in `pyvim/editor_buffer.py`. `mypy .` is clean (38 files); 55 tests pass.

### 1.4 Deviations & Fixes Beyond the Original Spec

| Item | Deviation / fix & rationale |
| :--- | :--- |
| **P0** | `ReporterError` has no `__eq__`, so `report_errors != self.report_errors` in `ready()` is instance-based: with unchanged text the freshly returned error list is re-published each background completion (the old errors stay rendered until completion, so the flicker is still gone). A content-based dedup would require adding `__eq__` to `ReporterError` — not adopted. |
| **P1** | The streaming path is behind a `_STREAMING_AVAILABLE` guard: `DocumentLexer` falls back to legacy `PygmentsLexer.from_filename` when `RegexSync`/`pygments_token_to_classname` are unavailable, and caches *misses* too, so unknown extensions don't re-scan the Pygments registry on every keystroke. |
| **P3** | Post-implementation follow-up (same changeset): `jedi` 0.20 removed the `Script(line=, column=)` constructor arguments and `completions()`. `_PythonCompleter` now detects the API via `inspect.signature(jedi.Script)` and calls `Script.complete(line, column)` on jedi ≥ 0.20 (and `completions()` on older jedi). The Jedi test skips when jedi is not installed. |
| **P4** | `TransformationInput.lineno` in prompt_toolkit 3.0.53 is **0-based** (`BufferControl._create_get_processed_line_func` → `get_processed_line(i)`, `i ∈ 0..line_count-1`), matching the 0-based `ReporterError.lineno`; `ReportingProcessor` therefore looks up `report_errors_by_line.get(transformation_input.lineno)` (no offset). `tests/test_layout.py` pins this exact semantics. |
| **P5** | `io.open` takes `encoding` as a **keyword** only (its 3rd positional parameter is `buffering`): `io.open(location, 'r', encoding=e)`. `:s` derives the cursor from a single `Document` — start-of-line plus that line's leading-whitespace count, replicating prompt_toolkit's `get_start_of_line_position(after_whitespace=True)` relative offset. |

---

## 2. P0: Fix Python 3.14+ `asyncio` Startup Crash, Reporter Lockup & Unnecessary Redraws

### Root Cause (`pyvim/editor_buffer.py:64-67, 174-217`, `pyvim/window_arrangement.py:403`)

In `pyvim/window_arrangement.py:403`[^src-window-arrangement], `_add_editor_buffer` calls `eb.run_reporter()` synchronously when creating a buffer. During CLI startup (`pyvim foo.py`), `Editor.load_initial_files()` runs **before** `Editor.run()` starts `prompt_toolkit`'s `asyncio` event loop[^src-editor].

Inspecting `EditorBuffer.run_reporter` (`pyvim/editor_buffer.py:174-217`)[^src-editor-buffer] reveals four issues:

1. **Crash on Python 3.14 & 3.15**: Calling `asyncio.get_event_loop()` at line 191 when no event loop is running raises `RuntimeError: There is no current event loop in thread 'MainThread'`.
2. **Permanent Lockout on Unnamed Buffers**: When `self.location is None` (e.g., running `pyvim` with no arguments), line 177 sets `self._reporter_is_running = True` and line 185 returns early **without resetting `self._reporter_is_running = False`**. Even after saving the buffer as `:w foo.py`, `run_reporter()` never runs again.
3. **Must Keep `_reporter_is_running = False` on the `except RuntimeError` Path**: When deferring `run_reporter()` because no event loop is running yet, `self._reporter_is_running` **must remain `False`** (only set `self._reporter_is_running = True` *after* `asyncio.get_running_loop()` succeeds).
4. **Background Thread + Full Redraw on Non-Python Files & Flicker on `.py` Files**:
   * `report(location, document)` (`pyvim/reporting.py:33`)[^src-reporting] only checks `location.endswith('.py')` *inside* the executor thread, so editing `.md`, `.json`, or `.txt` files still spawns thread-pool jobs and calls `get_app().invalidate()` on every keystroke.
   * On `.py` files, line 180 clears `self.report_errors = []` *before* starting the background check, causing red error lines to flicker on every keystroke.

### Solution (`pyvim/editor_buffer.py`, `pyvim/editor.py`)

In `EditorBuffer.__init__` (`pyvim/editor_buffer.py:64-67`):
```python
        # List of reporting errors and line index.
        self.report_errors = []
        self.report_errors_by_line = {}
        self._reporter_is_running = False
        self._run_reporter_again = False
```

And in `EditorBuffer.run_reporter` (`pyvim/editor_buffer.py:174-217`), preserving the exact `report(location, document)` argument order (`pyvim/reporting.py:33`) and `loop.call_soon_threadsafe(ready)` main-thread dispatch (`pyvim/editor_buffer.py:210`):

```python
    def run_reporter(self):
        " Buffer text changed. "
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
        if PTK3:
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
        document = self.buffer.document

        def in_executor():
            # Call reporter with (location, document) matching reporting.py:33
            report_errors = report(location, document)

            def ready():
                self._reporter_is_running = False

                # If the text has not changed while running in the worker thread,
                # update report_errors and only invalidate the UI if errors changed.
                if text == self.buffer.text and not self._run_reporter_again:
                    if report_errors != self.report_errors:
                        self.report_errors = report_errors
                        by_line = {}
                        for err in report_errors:
                            by_line.setdefault(err.lineno, []).append(err)
                        self.report_errors_by_line = by_line
                        get_app().invalidate()
                else:
                    self._run_reporter_again = False
                    self.run_reporter()

            if PTK3:
                loop.call_soon_threadsafe(ready)
            else:
                call_from_executor(ready)

        if PTK3:
            loop.run_in_executor(None, in_executor)
        else:
            run_in_executor(in_executor)
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
   `DocumentLexer.lex_document(document)` calls `PygmentsLexer.from_filename(location, sync_from_start=False)` on every buffer change, scanning Pygments' global lexer registry (`~0.6 ms` per call) and discarding the lexer instance.
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

### Solution (`pyvim/lexer.py` Using Public APIs Only)

Instead of subclassing `PygmentsLexer` or chunking `get_tokens_unprocessed` (which would reset Pygments' state machine across chunk boundaries inside multiline triple-quoted strings), `DocumentLexer` (`class DocumentLexer(Lexer)` in `pyvim/lexer.py`[^src-lexer]) uses **only public `pygments` and `prompt_toolkit` APIs**:
* `pygments.lexers.get_lexer_for_filename`
* `pygments_lexer.get_tokens_unprocessed(text)` (as a **single continuous generator** from `start_lineno` so multiline strings/docstrings never reset mid-token)
* `prompt_toolkit.lexers.pygments.RegexSync` (exported in `prompt_toolkit.lexers.pygments.__all__`)
* `prompt_toolkit.formatted_text.utils.split_lines` (streaming lazily from `get_text_fragments()` without `list(...)`)
* `prompt_toolkit.styles.pygments.pygments_token_to_classname`

Verified in `tools/bench_plans.py`[^src-bench]:
* **Multiline docstring parity**: 100% token-for-token match with `PygmentsLexer` across a 50-line multiline docstring spanning lines `80..130`.
* **Top of 4,000-line `.py` file**: `131.81 ms` $\rightarrow$ **`1.54 ms` (~85x faster)**
* **Middle (line 2,000) of 4,000-line `.py` file**: `69.49 ms` $\rightarrow$ **`3.33 ms` (~21x faster)**

---

## 4. P2: Defer Both `get_all_styles()` and Style Compilation at Startup

### Root Cause (`pyvim/style.py:33-37`, `pyvim/editor.py:80-81`, `pyvim/commands/completer.py:59`)

In `pyvim/editor.py:80-81`[^src-editor]:
```python
self.styles = generate_built_in_styles()
self.current_style = get_editor_style_by_name('vim')
```
`generate_built_in_styles()` calls `pygments.styles.get_all_styles()`, which invokes `find_plugin_styles()` (scanning `importlib.metadata` entry points across all installed packages, costing `~1.2–48 ms` depending on filesystem/VM speed) and then imports and compiles all **50** Pygments styles into `Style` objects (`17.87 ms` on macOS arm64; `~57 ms` on Linux x86_64). Yet `self.editor.styles` is only ever iterated in `ColorSchemeCompleter.get_completions` (`pyvim/commands/completer.py:59`: `for style_name in self.editor.styles:`)[^src-cmd-completer] when the user types `:colorscheme <Tab>`.

### Solution (`pyvim/style.py`)

Return a `_LazyStylesDict` (`collections.abc.Mapping`) from `generate_built_in_styles()` that defers **both** `list(get_all_styles())` and `get_editor_style_by_name(name)` until `self.styles` is actually iterated or indexed:

```python
class _LazyStylesDict(Mapping):
    def __init__(self):
        self._names = None
        self._loaded = {}

    def _ensure_names(self):
        if self._names is None:
            self._names = list(get_all_styles())
        return self._names

    def __iter__(self):
        return iter(self._ensure_names())

    def __len__(self):
        return len(self._ensure_names())

    def __getitem__(self, name):
        if name not in self._loaded:
            self._loaded[name] = get_editor_style_by_name(name)
        return self._loaded[name]
```

Measured in `tools/bench_plans.py`[^src-bench]: cold startup style initialization drops from **`17.87 ms` (`~57 ms` on Linux x86_64) to `0.09 ms`**.

---

## 5. P3: Singleton & Line-Cached `DocumentWordsCompleter`

### Root Cause (`pyvim/completion.py:12-55`)

In `pyvim/completion.py`[^src-completion]:
1. `DocumentCompleter.get_completions` (line 30) instantiates a brand-new `DocumentWordsCompleter()` on every single completion invocation, so any instance-level cache on `DocumentWordsCompleter` would never hit unless the completer instance is persisted.
2. `DocumentWordsCompleter.get_completions` runs `re.split(r'\W', document.text)` across the entire file on every keystroke (`3.12 ms` on a 4,000-line file).

### Solution (`pyvim/completion.py`)

1. Instantiate `self._words_completer = DocumentWordsCompleter()` **once** inside `DocumentCompleter.__init__`.
2. Inside `DocumentWordsCompleter`, cache the sorted unique words from all **non-cursor lines** keyed by `(len(doc_lines), cursor_row, prefix_text, suffix_text)`. While the user is typing on the current line `cursor_row`, `prefix_text` and `suffix_text` are unchanged, so each keystroke only regex-scans `doc_lines[cursor_row]` (1 line) and binary-searches (`bisect.bisect_left`) the pre-sorted `_other_words_sorted` list:
   * **Measured cost (`tools/bench_plans.py`)**: Drops per-keystroke completion latency on a 4,000-line file from **`3.12 ms` to `0.182 ms` (~17–23x faster)**[^src-bench].

---

## 6. P4: `O(1)` Line Index for `ReportMessageToolbar` & `ReportingProcessor`

### Root Cause (`pyvim/layout.py:272-293, 627-645`)

In `pyvim/layout.py`[^src-layout]:
* `ReportMessageToolbar` (`pyvim/layout.py:272-293`, inner function `get_formatted_text`) loops over `for e in errors:` on every render frame to find an error matching `eb.buffer.document.cursor_position_row`.
* `ReportingProcessor.apply_transformation` (`pyvim/layout.py:627-645`) loops over `for error in self.editor_buffer.report_errors:` on every visible line of every render frame, and calls `fragments = explode_text_fragments(fragments)` inside the `if error.lineno == transformation_input.lineno:` branch (using style `'class:flakeserror'` at line 643).

### Solution (`pyvim/layout.py`, `pyvim/editor_buffer.py`)

Use `self.report_errors_by_line: dict[int, list[ReporterError]]` on `EditorBuffer` (populated once when `ready()` receives new errors from the background thread):

```python
class ReportingProcessor(Processor):
    """
    Highlight all pyflakes errors on the input.
    """
    def __init__(self, editor_buffer):
        self.editor_buffer = editor_buffer

    def apply_transformation(self, transformation_input):
        fragments = transformation_input.fragments
        errors = self.editor_buffer.report_errors_by_line.get(
            transformation_input.lineno
        )
        if errors:
            fragments = explode_text_fragments(fragments)
            for error in errors:
                for i in range(error.start_column, error.end_column):
                    if i < len(fragments):
                        fragments[i] = ('class:flakeserror', fragments[i][1])

        return Transformation(fragments)
```

And in `ReportMessageToolbar` (`pyvim/layout.py:278-288`):
```python
        def get_formatted_text():
            eb = editor.window_arrangement.active_editor_buffer
            lineno = eb.buffer.document.cursor_position_row
            errors = eb.report_errors_by_line.get(lineno)
            if errors:
                return errors[0].formatted_text
            return []
```

---

## 7. P5: `codecs.open` Deprecation (Python 3.14+) & Minor Render/Command Cleanups

1. **Replace Deprecated `codecs.open` with `io.open` (`pyvim/io/backends.py:33-57`)**[^src-backends]:
   Python 3.14 officially deprecated `codecs.open()` ("use `open()` instead of `codecs.open()`"). Replacing `codecs.open(path, ...)` with built-in `io.open(path, ...)` removes the deprecation warning and uses CPython's C-buffered `BufferedReader`/`TextIOWrapper`.
2. **Avoid Double `Document(new_text)` Construction in `:s` (`pyvim/commands/commands.py:747-750`)**[^src-commands]:
   In `substitute()`, each matching line in `:s` constructs `Document(new_text)` twice (once to compute `translate_row_col_to_index(i, 0)`, then again with `cursor_position`). Computing the cursor index from a single `Document` cuts `Document` allocations during `:%s` in half.
3. **Cache `has_unsaved_changes` Boolean (`pyvim/editor_buffer.py:74-78`)**[^src-editor-buffer]:
   While CPython's equal-length `str != str` is fast (`~2.4 µs` for 100 KB), `has_unsaved_changes` is queried multiple times per frame in `WindowStatusBar` and tab titles. Updating a `self._has_unsaved_changes` flag on `on_text_changed`, `write()`, and `reload()` makes per-frame checks strictly `O(1)`.

---

## References

[^src-editor]: `pyvim/editor.py` (`Editor.__init__`, `Editor.run`) — [../pyvim/editor.py](../pyvim/editor.py)
[^src-editor-buffer]: `pyvim/editor_buffer.py` (`EditorBuffer.__init__`, `EditorBuffer.has_unsaved_changes`, `EditorBuffer.run_reporter`) — [../pyvim/editor_buffer.py](../pyvim/editor_buffer.py)
[^src-window-arrangement]: `pyvim/window_arrangement.py` (`WindowArrangement._add_editor_buffer`) — [../pyvim/window_arrangement.py](../pyvim/window_arrangement.py)
[^src-layout]: `pyvim/layout.py` (`ReportMessageToolbar`, `ReportingProcessor`, `EditorLayout`) — [../pyvim/layout.py](../pyvim/layout.py)
[^src-lexer]: `pyvim/lexer.py` (`DocumentLexer.lex_document`) — [../pyvim/lexer.py](../pyvim/lexer.py)
[^src-reporting]: `pyvim/reporting.py` (`report`) — [../pyvim/reporting.py](../pyvim/reporting.py)
[^src-completion]: `pyvim/completion.py` (`DocumentCompleter`, `DocumentWordsCompleter`) — [../pyvim/completion.py](../pyvim/completion.py)
[^src-style]: `pyvim/style.py` (`generate_built_in_styles`, `get_editor_style_by_name`) — [../pyvim/style.py](../pyvim/style.py)
[^src-cmd-completer]: `pyvim/commands/completer.py` (`ColorSchemeCompleter.get_completions`) — [../pyvim/commands/completer.py](../pyvim/commands/completer.py)
[^src-commands]: `pyvim/commands/commands.py` (`substitute`) — [../pyvim/commands/commands.py](../pyvim/commands/commands.py)
[^src-backends]: `pyvim/io/backends.py` (`FileIo`, `GZipFileIo`) — [../pyvim/io/backends.py](../pyvim/io/backends.py)
[^src-bench]: `tools/bench_plans.py` (Reproducible cell-cluster & latency benchmark script) — [../tools/bench_plans.py](../tools/bench_plans.py)
[^src-tests]: `tests/test_editor_buffer.py`, `tests/test_lexer.py`, `tests/test_style.py`, `tests/test_completion.py`, `tests/test_layout.py`, `tests/test_io_backends.py` (unit tests pinning P0–P5 behaviour, added in hg rev 161) — [../tests/](../tests/)
[^src-mypy]: `mypy.ini` (mypy baseline: `python_version = 3.15`, `ignore_missing_imports`; added in hg rev 162) — [../mypy.ini](../mypy.ini)
