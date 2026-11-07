---
type: index
title: "pyvim Findings Bundle"
description: "OKF v0.2 findings bundle for the pyvim bug audit: 61 machine-verified findings across Round 1 (hg rev 164, 2026-11-06, 001–037, closed) and Round 2 (hg rev 191, 2026-11-07, 038–061, fixed)."
status: stable
sources:
  - docs/bugs/
  - docs/
verified: machine-confirmed
stale_after: 2027-01-01T00:00:00Z
tags: [bugs, findings, audit]
generated:
  by: "Antigravity (Gemini 4 Argon)"
  at: "2026-11-07T07:28:00Z"
timestamp: "2026-11-07T07:28:00Z"
---

# pyvim Findings Bundle

This bundle tracks machine-verified audit findings for `pyvim` (`pyvim/`,
`tests/`, `tools/`, `setup.py`, and verification of the implemented plans in
[`../thai_support_plan.md`](../thai_support_plan.md) /
[`../speed_latency_plan.md`](../speed_latency_plan.md)):

* **Round 1 (2026-11-06, hg rev 164 — [001](001.md)–[037](037.md), `fix_status: fixed`)**: 16 defects and 21 improvements verified against `prompt_toolkit 3.0.53`, live micro-probes, the test suite (68 passed), `mypy .` (40 files clean), and `tools/bench_plans.py`. Closed in hg rev 167–195 (100 tests, 43-file mypy baseline at the 3.10 floor, ruff clean).
* **Round 2 (2026-11-07, hg rev 191 — [038](038.md)–[061](061.md), `fix_status: fixed`)**: 17 defects ([038](038.md)–[054](054.md)) and 7 improvements ([055](055.md)–[061](061.md)) uncovered during the follow-up full-project audit at hg rev 191 (`369831e8f7b8`). All fixed in hg rev 194–230.

## Round 2 Findings (2026-11-07, hg rev 191 → fixed in rev 194–230)

### Defects (`type: bug`, `fix_status: fixed`)

| ID | Finding | Area | Priority |
| :--- | :--- | :--- | :--- |
| [038](038.md) | `_delete_cell_clusters` raises `UnboundLocalError` on `X` at column 0 or `x` on an empty line | key-bindings/thai | **high** |
| [039](039.md) | `indent_line` (`<C-t>` in Insert mode) raises `AttributeError: 'KeyPressEvent' object has no attribute 'application'` | key-bindings | **high** |
| [040](040.md) | `TabPage._close_window` closes `active_window` instead of target `window` and mutates splits during iteration | window-arrangement | **high** |
| [041](041.md) | `WindowArrangement.close_window` (`:hide`) on the last window of a tab leaves an empty `VSplit` and crashes rendering | window-arrangement/layout | **high** |
| [042](042.md) | Visual mode (`v`) slices Thai/Lao cell clusters in half and ignores cell-cluster motions | thai/visual-mode | **high** |
| [043](043.md) | Inclusive Vi motions (`dge`, `dgE`, `df`, `dt`, `dT`) slice Thai/Lao cell clusters and fuse combining marks | thai/motion | **high** |
| [044](044.md) | `DocumentWordsCompleter` regex (`\w+`) strips Thai/Lao combining marks (`GC=Mn`) and fails to complete Thai words | completion/thai | **high** |
| [045](045.md) | `report_pyflakes` treats `pyflakes` UTF-8 byte `col_offset` as codepoint index and restricts identifiers to ASCII | reporting/unicode | medium |
| [046](046.md) | `ReporterError` lacks `__eq__`, defeating `report_errors != self.report_errors` deduplication in `run_reporter` | reporting/redraw | medium |
| [047](047.md) | `:cd` without an argument raises uncaught `TypeError` and skips `os.path.expanduser` | commands/io | medium |
| [048](048.md) | `substitute` (`:s`) raises uncaught `re.error` on invalid regex or replacement escapes | commands/substitute | medium |
| [049](049.md) | Opening `~` or `~/dir` fails with `IsADirectoryError` because `DirectoryIO` and `FileIO.can_open_location` omit `expanduser` | io/file-explorer | medium |
| [050](050.md) | `EditorBuffer.write` and `:w` mutate `location` before validation, skip `expanduser` on overwrite check, and miss reporter/lexer refresh | io/editor-buffer/lexer | medium |
| [051](051.md) | `:colo <scheme>` is registered in `commands.py` but rejected by `COMMAND_GRAMMAR` and ignored by `CommandPreviewer` | commands/grammar/preview | low |
| [052](052.md) | `BufferListOverlay` checks `location in c.display` (`FormattedText` list, always `False`) and triggers on `:buffers` | layout/completion | low |
| [053](053.md) | `reverse_case_cell` (`~`) overrides `:set tildeop` unconditionally and ignores `event.arg` | key-bindings/vi-mode | low |
| [054](054.md) | Miscellaneous logic defects (`is_thai_base` digits, `close_buffer` tab index, `hsplit`/`vsplit` assert, preview mismatches, `ignorecase`, file explorer, `tabstop`, `_try_char`) | thai/window-arrangement/commands/layout | low |

### Improvements & cleanup (`type: improvement`, `fix_status: fixed`)

| ID | Finding | Category | Priority |
| :-- | :--- | :--- | :--- |
| [055](055.md) | `substitute` (`:s`) runs `re.sub` twice per line and rebuilds `Document` on zero matches | performance | medium |
| [056](056.md) | `_ThaiTextGate.note` scans the whole buffer per keystroke on non-ASCII non-Thai files, and word motions check `doc.text.isascii()` | performance | medium |
| [057](057.md) | `DocumentLexer` joins lines to EOF per edit and `_sanitize_and_invalidate_sara_am` inflates sparse `Screen.data_buffer` rows/columns | performance | low |
| [058](058.md) | Dead code inventory (round 2: `_current_window_for_event`, `TABSTOP_DOT`, unreachable `ENCODINGS` fallbacks, `_buffer` param, `ignore_case`, `_gate_fixture`) | dead code | low |
| [059](059.md) | Duplicate code and logic inventory (round 2: duplicated comment block, `ENCODINGS` loop, `FileIO()` instantiation, redundant filter, active buffer lookup) | duplication | low |
| [060](060.md) | Readability and test hygiene inventory (round 2: 1-tuple `super`, `cls` parameter, `bytes` shadowing, docstrings, `__import__`, `conftest` `~/.pyvim`) | readability/hygiene | low |
| [061](061.md) | Plan and benchmark drift (round 2: corrupted code fence in `thai_support_plan.md`, P2 `bench_plans.py` calculation, stale metadata) | documentation/benchmark | low |

---

## Round 1 Closed Findings (2026-11-06, hg rev 164 → fixed in rev 167–195)

**Resolution note (2026-11-06 fix arc):** every Round 1 finding below has been
fixed and machine-re-verified (hg rev 167–195: 100 tests,
43-file mypy baseline at the 3.10 floor, ruff clean, bench reproducing). Each
document's frontmatter carries `fix_status: fixed (hg rev N)`; the fix-verdict
revisions are also summarized in [`log.md`](log.md).

### Defects (`type: bug`, `fix_status: fixed`)

| ID | Finding | Area | Priority |
| :--- | :--- | :--- | :--- |
| [001](001.md) | Thai/Lao word motions re-segment the whole document per motion key (~640 ms/`w` on 2.4 MB) | thai/motion | **high** |
| [002](002.md) | SARA-AM sanitizer full-screen scan per frame even for ASCII-only content (1.27 ms/frame) | thai/renderer | **high** |
| [003](003.md) | Uncaught `ImportError` on Tab for `.py` buffers without jedi (jedi is optional, flag default-on) | completion | medium |
| [004](004.md) | `:<n>s/…` with a range beyond EOF raises uncaught `IndexError` | commands | medium |
| [005](005.md) | Version-gate rollback incomplete: KeyProcessor patches survive a failed install | thai/patches | medium |
| [006](006.md) | `EditorBuffer.write()` writes via the last backend after "Unknown location" | io | low |
| [007](007.md) | `:wq` exits even when `:w` failed (data-loss risk) | commands | low |
| [008](008.md) | `tools/bench_plans.py` validates duplicated copies, not shipped code (4 drifted re-implementations) | tooling | medium |
| [009](009.md) | Command grammar regex built from an unordered set | commandline | low |
| [010](010.md) | Duplicated `.py` gating (`run_reporter` vs `report`) | reporting | low |
| [011](011.md) | Pyflakes columns are source-space but highlight happens in post-tab fragment space | reporting/layout | medium |
| [012](012.md) | Toolbar shows only `errors[0]` per line | layout | low |
| [013](013.md) | New buffer inserted *before* active; comment says after (`:buffers` numbering) | window-arrangement | low |
| [014](014.md) | Cross-line cluster-walk safety rides on an undocumented `is_combining_char` invariant | thai | low |
| [015](015.md) | `:1,3s/…` cursor targets end-of-range even without substitutions (upstream FIXME) | commands | low |
| [016](016.md) | `loop` bound only on the PTK3 branch in `run_reporter` | reporter | low |

### Improvements & cleanup (`type: improvement`, `fix_status: fixed`)

| ID | Finding | Category | Priority |
| :-- | :--- | :--- | :--- |
| [017](017.md) | `pyvim/enums.py` empty, never imported | dead code | low |
| [018](018.md) | `PyvimScrollOffsets` unused (ScrollOffsets takes callables) | dead code | low |
| [019](019.md) | `get_terminal_title` dead since its comment-only caller | dead code | low |
| [020](020.md) | `get_editor_buffer_for_buffer_name` dead + would `AttributeError` | dead code | low |
| [021](021.md) | unused import `fragment_list_len` | dead code | low |
| [022](022.md) | write-only attribute `editor.file_explorer` | dead code | low |
| [023](023.md) | dead identical if/return branches (thai `_start_timeout` wrapper) | dead code | low |
| [024](024.md) | unreachable second `find_closest_generator` call | dead code | low |
| [025](025.md) | stale `.travis.yml` (2.7/3.5/3.6, defunct service) | legacy/CI | low |
| [026](026.md) | `pyvim.egg-info/` debris; repo lacks `.hgignore` | hygiene | low |
| [027](027.md) | `six` + 26× `unicode_literals` py2 legacy weight | legacy | low |
| [028](028.md) | `:set` option map duplicated (commands vs preview) | duplication | low |
| [029](029.md) | near-clone pairs: `e`/`E`, `x`/`X`, cursor up/down, int setters | duplication | low |
| [030](030.md) | extra hot paths: explorer lexer, to-EOF join, jedi introspection, key slices | performance | low |
| [031](031.md) | `mypy.ini python_version = 3.15` vs the 3.10 floor | compatibility | low |
| [032](032.md) | `setup.py` missing `python_requires` / metadata | packaging | low |
| [033](033.md) | 27 lambdas vs the no-lambda coding rule | readability | low |
| [034](034.md) | typo / copy-paste docstring inventory | readability | low |
| [035](035.md) | docs-bundle drift: plan sections, index counts, bench citations | documentation | low |
| [036](036.md) | CHANGELOG/README omit 2026 arc, point upstream | documentation | low |
| [037](037.md) | venv lacks pytest/mypy; claims not reproducible in-repo | toolchain | low |

## Verification note

Python **3.11+ syntax scan**: `None found` — all modules parse under
`ast.parse(feature_version=(3, 10))`; the only floor-related issues are the
configuration/packaging ones above ([031](031.md), [032](032.md)).

## Meta

* [Bundle Update Log](log.md) — chronological log of this bundle.
* Root bundle: [`../index.md`](../index.md).
