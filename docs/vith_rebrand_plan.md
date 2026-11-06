---
type: project_priority
title: "Vith re-brand & Python-packaging modernization plan (formerly pyvim)"
description: "Execution plan for the 2026-11 identity change: pyvim -> vith (วิธ), BSD 3-clause kept with stacked copyright, setup.py -> pyproject.toml (PEP 621), README.rst -> README.md, user-data migration, docs sweep, and gate re-verification. Decisions already locked are listed; the three open choices are marked."
status: draft
sources:
  - ../setup.py
  - ../README.rst
  - ../pyvim
  - ../tests
  - ../tools
verified: machine-confirmed
stale_after: 2026-12-15T00:00:00Z
tags: [rebrand, packaging, pyproject, readme, planning]
generated:
  by: "opencode/glm-5.3-flash"
  at: "2026-11-06T16:27:00Z"
timestamp: "2026-11-06T16:27:00Z"
---

# Vith re-brand & packaging modernization plan

[🧭 Docs root](index.md) · sibling bundles: [Findings (closed)](bugs/index.md) · [Speed plan](speed_latency_plan.md) · [Thai plan](thai_support_plan.md)

## 1. Identity decision (locked 2026-11-06)

* **New name**: `vith`, Thai spelling **วิธ** — from วิธี (Pali/Skt *vidhi*, "method"); the วิ- prefix (as in วิวิธ, พิพิธ) adds "manner, kind, various". Also the natural overlap portmanteau of **ViM + THAi**.
* **Fork relation**: broken at the identity layer only. "Formerly known as pyvim (by Jonathan Slenders)" stays in README/CHANGELOG heritage lines.
* **License**: **BSD 3-clause kept** — do *not* relicense to MIT (the tree is derived work; the original notice must persist). LICENSE becomes stacked per the owner's convention used in `talyn`/`active-boxes`:

```text
Copyright (c) 2015, Jonathan Slenders
Copyright (c) 2026, Chaiwat Suttipongsakul
All rights reserved.
... (BSD 3-clause body unchanged)
```

* `setup.py` stays BSD + gains author **Chaiwat Suttipongsakul** (`<cwt@bashell.com>`), replacing the upstream-only author field.
* Runtime experiments retired in the same arc (2026-11-06): alternate event loops (uvloop/talyn — findings filed in the **talyn** repo BUG-416..418), free-threaded CPython, PyPy. All evidence recorded in this bundle's log; **none** of them change pyvim/vith code.

## 2. Verified prerequisites (2026-11-06)

| Fact | Evidence |
|---|---|
| PyPI name `vith` **unclaimed** | `pip index versions vith` → "No matching distribution found" |
| Gates currently green | tip rev 196 `eaad74795024`: 100 tests, mypy 43 files @3.10, ruff check+format clean |
| Bench baseline holds | `tools/bench_plans.py`: P1a 1.21 ms / P2 0.15 ms / P3 0.030 ms |
| License chain | `LICENSE` = BSD 3-clause © 2015 Jonathan Slenders — retained |
| Hg identity | all commits are already `Chaiwat Suttipongsakul <cwt@bashell.com>` |

## 3. Work items

### W1 — package rename (`hg mv`, history-preserving)

1. `hg mv pyvim vith` (keeps filelog history through Mercurial; hg-git mirror unaffected — bookmarks unchanged).
2. Internal import sweep `pyvim\.` → `vith\.` across `vith/`, `tests/`, `tools/` (14 test files + `tools/bench_plans.py` import `pyvim.*`).
3. Fingerprints on third-party objects (visible global marks, zero functional impact):
   - `_pyvim_thai_patched` → `_vith_thai_patched` (`vith/thai.py`, `tests/test_thai.py`)
   - `_pyvim_original` → `_vith_original`
   - `__pyvim_sara_am_invalidate__` → `__vith_sara_am_invalidate__` (`_SARA_AM_POISON` style string)
4. `docopt` usage string: `vith/entry_points/run_pyvim.py` docstring is *the docopt spec* (`docopt(__doc__)`) — rewrite its usage/options text to `vith [-p] [-o] [-O] [-u <vithrc>] [<location>...]`.
5. `examples/config/pyvimrc` → `examples/config/vithrc`.

### W2 — packaging: setup.py → pyproject.toml (PEP 621) [open item from the arc]

Replace `setup.py` entirely; keep `pyproject.toml` as single source (it already holds `[tool.ruff]`):

```toml
[build-system]
requires = ["setuptools>=77", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "vith"
description = "Vith — a pure-Python Vi clone with Thai & Lao script support (formerly pyvim)"
readme = "README.md"
license = "BSD-3-Clause"          # SPDX expression (PEP 639-style table). Keep the full
                                   # text in LICENSE; setuptools includes it from file.
authors = [{ name = "Chaiwat Suttipongsakul", email = "cwt@bashell.com" }]
requires-python = ">=3.10"
dependencies = [
    "prompt_toolkit>=3.0.0,<3.1.0",
    "pyflakes",
    "pygments",
    "docopt",
]
dynamic = ["version"]
classifiers = ["Intended Audience :: Developers", "Topic :: Text Editors", ...]

[project.scripts]
vith = "vith.entry_points.run_pyvim:run"

[tool.setuptools.packages.find]
include = ["vith*"]

[tool.setuptools.dynamic]
version = { attr = "vith.__version__" }
```

Notes:
* **No `pyvim` console entry** — installing upstream pyvim side-by-side must not collide on a binary name.
* `[tool.ruff]` stays untouched; move `mypy.ini` → `[tool.mypy]` **optional** (either is fine — pick one and note the choice in the `log`).
* Delete `setup.py` in the same commit that lands `pyproject.toml` so the packaging story has one source of truth.
* Keep `requirements-dev.txt` (pytest/mypy/ruff pins) as the dev toolchain file.

### W3 — README: rst → markdown

1. `hg mv README.rst README.md` then convert:
   - `::` literal blocks + indentation → fenced ```code blocks```;
   - `.. image ::<url>` → `![alt](url)` (same repo image paths);
   - section underlines become `#/##` headers; the `|Build Status|` substitution block is already removed (rev ~196 era) — nothing left to carry.
2. Heritage header (rewrites the current fork note): **“vith (วิธ) — formerly pyvim, an implementation of Vim in Python by Jonathan Slenders”** + the Thai-name paragraph from §1.
3. **Fix the stale Limitations claim** while touching it: “files above ~1000 lines get noticeably slower” is pre-P1 text (removed since rev ~161); replace with the current bounded-cost paragraph (bench `P1a 1.21 ms`).
4. Testing section: point at `requirements-dev.txt`, `python -m pytest tests`, `mypy .`, `ruff check`, `python tools/bench_plans.py`.

### W4 — user data & rc migration [decision OPEN — recommendation: graceful fallback]

Current anchors:
* `Editor.__init__(config_directory='~/.pyvim', ...)` (`vith/editor.py:45`, config dir + `commands_history`/`search_history` files at `:108/:118`)
* default rc path `~/.pyvimrc` in `vith/entry_points/run_pyvim.py`

Recommended behavior after rename:
* default config dir `~/.vith`; on session start, if `~/.vith` missing **and** `~/.pyvim` exists → reuse legacy dir contents (copy on first write, or read-through) — zero friction for the maintainer's own setup;
* `.vithrc` default, fallback read `~/.pyvimrc`;
* log a one-line notice only when a legacy fallback actually was used.

### W5 — identity strings sweep (grep-able list)

* `vith/welcome_message.py`: `('class:title', 'PyVim - Pure Python Vi clone\n')` → Vith wording; `by Jonathan Slenders` credit → “from the pyvim project by Jonathan Slenders” (credit preserved); `import pyvim`/`pyvim.__version__` → `vith`.
* `vith/help.py` header “PyVim Help” → “Vith”.
* residue scan after sweep: `grep -rwn pyvim` should return **only** historical docs + `CHANGELOG` appendix mentions.

### W6 — version lineage [decision OPEN — recommendation: reset to 1.0.0]

* Reset: `vith.__version__ = '1.0.0'`; `CHANGELOG` gains a top section “1.0.0 — first release as vith (formerly pyvim 3.x)” followed by a verbatim **“History under the pyvim name”** appendix (3.0.3 and older entries kept verbatim).
* Continue-3.x was the alternative; reset was argued cleaner for the new identity — final call at execution.

### W7 — docs sweep (mechanical; keep history true)

* The two plan bundles (`thai_support_plan.md`, `speed_latency_plan.md`) and `bugs/*` were authored under the pyvim name — **treat their `../pyvim/...` source links as historical, not stale**: add a one-paragraph name-mapping note (“documents below refer to the package as pyvim; since the 2026-11 rebrand those paths are vith/…”) to `index.md` of each bundle.
* Going forward, new references use `../vith/…`; `docs/index.md` gets the rebrand note + the vith-rename row appended to `log.md` at execution time.
* CI/tooling text in `README`/`docs` that says “pyvim” updates mechanically.

### W8 — verification gates (must all pass before the commits)

1. `python -m pytest tests` — expect the same `100 passed` (plus any jedi-conditional skip parity),
2. `mypy .` — no issues, 43 files @ `python_version=3.10`,
3. `ruff check` + `ruff format --check .` — clean,
4. `python tools/bench_plans.py` — P1a ≈1.2 ms, P2 ≈0.15 ms, P3 ≈0.03 ms (no regression from the rename),
5. boot smoke: full Editor + `PosixPipeInput(':q\n')` exits cleanly,
6. `vithrc` fallback path test if W4 fallback implemented.

## 4. Commit plan (2–3 commits)

1. `rebrand: pyvim -> vith (package, entries, markers, identity strings, license stack)` — W1/W2-license/W4/W5 + gate progression,
2. `packaging: setup.py -> pyproject.toml (PEP 621); README.rst -> README.md` — W2/W3,
3. `docs: name-mapping notes across OKF bundles; changelog history appendix` — W7 (+ W6 depending on the chosen version).

## 5. Open decisions at execution

| Decision | Recommendation | Alternatives |
|---|---|---|
| User-data migration | graceful fallback to `~/.pyvim*` | hard cutover / keep legacy paths |
| Version lineage | reset to `1.0.0` | continue 3.x, or start 0.x |
| mypy config location | keep `mypy.ini` as-is | fold into `pyproject` `[tool.mypy]` |
| PyPI registration | manual step on the owner's account (`vith` slot verified free) | — |

[^src]: package tree, `setup.py`, `README.rst`, `CHANGELOG`, `docs/` — all anchors listed inline above.
