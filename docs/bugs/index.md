---
type: index
title: "pyvim Findings Bundle"
description: "OKF v0.2 findings bundle for the pyvim bug audit: 37 machine-verified findings from the deep review at hg rev 164 (2026-11-06)."
status: stable
sources:
  - docs/bugs/
  - docs/
verified: machine-confirmed
stale_after: 2027-01-01T00:00:00Z
tags: [bugs, findings, audit]
generated:
  by: "OpenCode (GLM-5.3-Flash)"
  at: "2026-11-06T12:12:00Z"
timestamp: "2026-11-06T12:12:00Z"
---

# pyvim Findings Bundle

Findings from the 2026-11-06 deep review of the pyvim codebase (`pyvim/`,
`tests/`, `tools/`, `setup.py`, and verification of the implemented plans in
[`../thai_support_plan.md`](../thai_support_plan.md) /
[`../speed_latency_plan.md`](../speed_latency_plan.md)).

Verified against prompt_toolkit 3.0.53 source, live micro-probes, the test
suite (68 passed), `mypy .` (40 files clean) and `tools/bench_plans.py`
(figures reproduced). At review time no code was changed.

**Resolution note (2026-11-06 fix arc):** every finding below has since been
fixed and machine-re-verified (hg rev 167–195: 100 tests,
43-file mypy baseline at the 3.10 floor, ruff clean, bench reproducing). Each
document's frontmatter carries `fix_status: fixed (hg rev N)`; the fix-verdict
revisions are also summarized in [`log.md`](log.md).

## Defects (`type: bug`)

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

## Improvements & cleanup (`type: improvement`)

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
