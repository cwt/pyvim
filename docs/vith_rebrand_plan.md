---
type: project_priority
title: "Vith re-brand & Python-packaging modernization plan (formerly pyvim)"
description: "Execution plan for the 2026-11 identity change: pyvim -> vith (วิธ), BSD 3-clause kept with stacked copyright, setup.py -> pyproject.toml (PEP 621), README.rst -> README.md, user-data migration, docs sweep, and gate re-verification. Decisions already locked are listed; the open choices are marked."
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
timestamp: "2026-11-07T00:00:00Z"
---

# Vith re-brand & packaging modernization plan

[🧭 Docs root](index.md) · sibling bundles: [Findings (closed)](bugs/index.md) · [Speed plan](speed_latency_plan.md) · [Thai plan](thai_support_plan.md)

## 0. Repo identity: hg-git, hashes only

* This repo is Mercurial with **hg-git** as the GitHub client: `.hg/hgrc`
  `[paths] default = git+ssh://git@github.com:cwt/pyvim.git`
  (mirror `upstream = git@github.com:prompt-toolkit/pyvim.git`),
  bookmarks carry the `.git` suffix (e.g. `master.git`).
* **Never cite `rXXX` rev numbers** — they are local-only under hg-git and
  shift on re-clone/filter. Always cite the full 40-char Mercurial node id.
* Current anchors: tip `70f07667abd7a086ba56702e1f2b68987fbaa175`
  ("docs: file the vith re-brand plan"), parent
  `eaad747950240f98e0d3011e0599beb17c6f76fe`
  (gates green: 100 tests, mypy 43 files @3.10, ruff clean).

## 1. Identity decision (locked 2026-11-06, amended 2026-11-07)

* **New name**: `vith`, Thai spelling **วิธ** — from วิธี (Pali/Skt *vidhi*, "method"); the วิ- prefix (as in วิวิธ, พิพิธ) adds "manner, kind, various". Also the natural overlap portmanteau of **ViM + THAi**.
* **Rename policy (locked 2026-11-07)**: rename **all** `pyvim` → `vith`
  (package, imports, entry points, config paths, docs, comments, asset
  filenames) **except**:
  1. the verbatim **"History under the pyvim name"** appendix in `CHANGELOG`
     (3.0.3 and older entries kept byte-for-byte), and
  2. explicit heritage sentences (README banner, CHANGELOG 1.0.0 preamble,
     one name-mapping note per docs bundle — see W3/W7).
* **Fork banner (required)**: `README.md` opens with a clear, obvious fork
  notice — **"vith (วิธ) — a fork of pyvim (by Jonathan Slenders), extended
  with Thai/Lao support and latency work"** — plus the Thai-name paragraph
  from §1. No silent rebrand.
* **License**: **BSD 3-clause kept** — do *not* relicense to MIT (the tree is
  derived work; the original notice must persist). LICENSE becomes stacked
  per the owner's convention used in `talyn`/`active-boxes`:

```text
Copyright (c) 2015, Jonathan Slenders
Copyright (c) 2026, Chaiwat Suttipongsakul
All rights reserved.
... (BSD 3-clause body unchanged)
```

* Runtime experiments retired in the same arc (2026-11-06): alternate event
  loops (uvloop/talyn — findings filed in the **talyn** repo BUG-416..418),
  free-threaded CPython, PyPy. All evidence recorded in this bundle's log;
  **none** of them change pyvim/vith code.

## 2. Verified prerequisites (2026-11-06, hash-corrected 2026-11-07)

| Fact | Evidence |
|---|---|
| PyPI name `vith` **unclaimed (re-check at execution)** | `pip index versions` is deprecated; use `https://pypi.org/pypi/vith/json` (404 = free) or `pip install vith==` probe |
| Gates currently green | parent `eaad747950240f98e0d3011e0599beb17c6f76fe`: 100 passed, mypy 43 files @3.10, ruff check+format clean |
| Bench baseline (same-machine only) | `python tools/bench_plans.py` here: P1a ~1.38 ms / P2 ~0.12 ms / P3 ~0.052 ms (plan's 1.21/0.15/0.030 were another machine — gate is *no regression on the same host*, not absolute values) |
| License chain | `LICENSE` = BSD 3-clause © 2015 Jonathan Slenders — retained, to be stacked |
| Hg identity | all commits are already `Chaiwat Suttipongsakul <cwt@bashell.com>` |
| Hg-git note | `hg paths`/`hg bookmarks` show `.git`-suffixed bookmarks; rev numbers are local — cite nodes (§0) |

## 3. Work items

### W1 — package rename (`hg mv`, history-preserving)

1. `hg mv pyvim vith` (keeps filelog history; hg-git mirror unaffected —
   bookmarks unchanged).
2. `hg mv vith/entry_points/run_pyvim.py vith/entry_points/run_vith.py`
   (the old filename contains the old identity; update its importers:
   `vith/__main__.py`, packaging `[project.scripts]`).
3. Internal import sweep `pyvim\.` → `vith\.` across `vith/`, `tests/`,
   `tools/` (13 `test_*.py` modules + `tests/conftest.py` + 
   `tools/bench_plans.py` import `pyvim.*` — 15 files total).
4. Fingerprints on third-party objects (visible global marks, zero functional impact):
   - `_pyvim_thai_patched` → `_vith_thai_patched`
     (`vith/thai.py`, `tests/test_thai.py`)
   - `_pyvim_original` → `_vith_original`
   - `__pyvim_sara_am_invalidate__` → `__vith_sara_am_invalidate__`
     (`_SARA_AM_POISON` style string)
5. Comment/docstring sweep (same `pyvim` → `vith` rename, not just code):
   `vith/__main__.py` ("`python -m pyvim`"), `vith/rc_file.py:4`,
   `vith/editor_buffer.py:47` ("see pyvim/thai.py"),
   `vith/editor.py:103` ("see pyvim/thai.py"),
   `vith/thai.py:1-20` module docstring + `_ThaiTextGate` docstring.
6. `docopt` usage string: `vith/entry_points/run_vith.py` docstring *is* the
   docopt spec (`docopt(__doc__)`) — rewrite to
   `vith [-p] [-o] [-O] [-u <vithrc>] [<location>...]` with `-u <vithrc>`
   help text.
7. `hg mv examples/config/pyvimrc examples/config/vithrc` **plus body**:
   `~/.pyvimrc` → `~/.vithrc`, ``pyvim.editor.Editor`` → ``vith.editor.Editor``.
8. `hg mv docs/images/editing-pyvim-source.png docs/images/editing-vith-source.png`
   and update its `README` reference (only asset filename containing the old name).

### W2 — packaging: setup.py → pyproject.toml (PEP 621)

Replace `setup.py` entirely **in the same commit as W1** (a rename-only
intermediate leaves `setup.py` doing `import pyvim` / `name='pyvim'` —
broken). Keep `pyproject.toml` as single source (it already holds `[tool.ruff]`):

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "vith"
description = "Vith — a pure-Python Vi clone with Thai & Lao script support (fork of pyvim)"
readme = "README.md"
license = { text = "BSD-3-Clause" }  # verify with `pip install -e .` + `python -m build`;
                                     # setuptools>=77 also accepts SPDX string form —
                                     # pick one, keep full text in LICENSE.
authors = [{ name = "Chaiwat Suttipongsakul", email = "cwt@bashell.com" }]
requires-python = ">=3.10"
dependencies = [
    "prompt_toolkit>=3.0.0,<3.1.0",
    "pyflakes",
    "pygments",
    "docopt",
]
# NOTE: jedi stays OPTIONAL (not in install_requires) — `vith/completion.py`
# imports it lazily via importlib; optionally add:
# [project.optional-dependencies]
# python = ["jedi>=0.19"]
dynamic = ["version"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: BSD Software License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Topic :: Text Editors",
    "Topic :: Text Editors :: Text Processing",
]
urls = { Homepage = "https://github.com/cwt/pyvim",
         Repository = "https://github.com/cwt/pyvim.git",
         Upstream = "https://github.com/jonathanslenders/pyvim" }

[project.scripts]
vith = "vith.entry_points.run_vith:run"

[tool.setuptools.packages.find]
include = ["vith*"]

[tool.setuptools.dynamic]
version = { attr = "vith.__version__" }
```

Notes:
* **No `pyvim` console entry** — installing upstream pyvim side-by-side must not collide on a binary name.
* `[tool.ruff.lint.isort] known-first-party` must change `["pyvim"]` →
  `["vith"]`; update the `pyproject.toml` header comment ("Packaging lives
  in setup.py" is stale). `requirements-dev.txt` header ("for pyvim") → vith.
* `[tool.mypy]` move **optional** — recommendation: keep `mypy.ini` as-is
  (decision table §5); either way note the choice in `docs/log.md`.
* Delete `setup.py` in the **same** commit as the W1 rename; `rm -rf`
  `pyvim.egg-info/` is untracked (`*.egg-info/` in `.hgignore`/`.gitignore`)
  — just regenerate, do not commit it.
* Keep `requirements-dev.txt` (pytest/mypy/ruff pins) as the dev toolchain file.

### W3 — README: rst → markdown (with obvious fork banner)

1. `hg mv README.rst README.md` then convert:
   - `::` literal blocks + indentation → fenced ```code blocks```;
   - `.. image :: <url>` (6 directives, note the stray space — invalid rst)
     → `![alt](url)` (same `docs/images/` paths, with the
     `editing-vith-source.png` rename from W1.8);
   - section underlines become `#/##` headers; `README.rst` itself has no
     `|Build Status|` badge left (the only remaining copy is the stale
     generated `pyvim.egg-info/PKG-INFO`, an ignored artifact — nothing to carry).
2. **First screen = fork banner (required, locked 2026-11-07)**:
   `# vith (วิธ) — a fork of pyvim` + one paragraph: upstream is
   "an implementation of Vim in Python by Jonathan Slenders",
   this fork adds Thai/Lao script support + latency/modern-Python work,
   BSD 3-clause retained with stacked copyright. Follow with the
   Thai-name paragraph from §1.
3. **Fix the stale Limitations claim** while touching it: "files above ~1000
   lines get noticeably slower" is pre-P1 text (removed since `024e7f40f812`
   era); replace with the current bounded-cost paragraph (same-machine
   `tools/bench_plans.py` figure, e.g. P1a ~1.3 ms top-40 of 4000 lines).
4. Testing section: point at `requirements-dev.txt`,
   `python -m pytest tests`, `mypy .`, `ruff check`,
   `ruff format --check .`, `python tools/bench_plans.py`.

### W4 — user data & rc migration [decision OPEN — recommendation: graceful fallback]

Current anchors:
* `Editor.__init__(config_directory='~/.pyvim', ...)` (`pyvim/editor.py:45`, config dir + `commands_history`/`search_history` files at `:108/:118`)
* default rc path `~/.pyvimrc` in `pyvim/entry_points/run_pyvim.py:39`

Recommended behavior after rename:
* default config dir `~/.vith`; on session start, if `~/.vith` missing **and** `~/.pyvim` exists → reuse legacy dir contents (copy on first write, or read-through) — zero friction for the maintainer's own setup;
* `.vithrc` default, fallback read `~/.pyvimrc`;
* log a one-line notice only when a legacy fallback actually was used.

### W5 — identity strings sweep (grep-able list)

* `vith/welcome_message.py`: `('class:title', 'PyVim - Pure Python Vi clone\n')` → Vith wording; `by Jonathan Slenders` credit → "from the pyvim project by Jonathan Slenders" (credit preserved); `import pyvim`/`pyvim.__version__` → `vith`.
* `vith/help.py` header "PyVim Help" → "Vith".
* Residue rule (revised 2026-11-07 for rename-all): after the sweep,
  `grep -rwn pyvim --include='*.py' --include='*.toml' --include='*.ini' --include='*.txt' vith tests tools examples` must be **empty**, and repo-wide `grep -rwn pyvim` must return **only**:
  1. `CHANGELOG` "History under the pyvim name" appendix (verbatim),
  2. the explicit heritage sentences (README banner, CHANGELOG 1.0.0 preamble, one name-mapping note per docs bundle).

### W6 — version lineage [decision OPEN — recommendation: reset to 1.0.0]

* Reset: `vith.__version__ = '1.0.0'`; `CHANGELOG` gains a top section
  "1.0.0 — first release as vith (formerly pyvim 3.x)" followed by a verbatim
  **"History under the pyvim name"** appendix (3.0.3 and older entries kept
  verbatim — this appendix is the one place the old name stays).
* Known wrinkle: `pyvim/__init__.py` says `3.0.3` while `CHANGELOG` already
  has an unreleased `3.0.4` section — resolve at execution (1.0.0 preamble
  absorbs the 3.0.4 content or copies it verbatim into the appendix).
* Trade-off recorded: `1.0.0` is cleaner for the new identity but `pip`
  will not auto-upgrade `3.x → 1.0.0`; `4.0.0` preserves the upgrade path.
  Final call at execution.

### W7 — docs sweep (rename-all; keep history true)

* Rename **all** live `pyvim` → `vith` in `docs/*.md` (including the
  `../pyvim/…` source links → `../vith/…`, `docs/index.md` bundle title,
  `thai_support_plan.md` / `speed_latency_plan.md` / `bugs/*` body text).
* Keep history true with an explicit note, not stale links: each bundle
  (`index.md` of root/thai/speed/bugs) gains a one-paragraph name-mapping
  note ("written under the pyvim name; since the 2026-11 rebrand those paths
  are vith/…; CHANGELOG appendix preserves the pyvim history verbatim").
* Going forward, new references use `../vith/…`; `docs/index.md` gets the
  rebrand note + the vith-rename row appended to `log.md` at execution time.

### W8 — verification gates (must all pass before the commits)

1. `python -m pytest tests` — expect the same `100 passed` (plus any jedi-conditional skip parity),
2. `mypy .` — no issues, 43 files @ `python_version=3.10`,
3. `ruff check` + `ruff format --check .` — clean,
4. `python tools/bench_plans.py` — no regression vs same-machine pre-rename
   baseline (do not gate on absolute 1.21/0.15/0.030 — those were another host),
5. boot smoke: full Editor + `PosixPipeInput(':q\n')` exits cleanly,
6. `vithrc` fallback path test if W4 fallback implemented,
7. `python -m build` + `pip install -e .` smoke (validates the PEP 621 TOML)
   and `vith --help` shows the new docopt usage.

## 4. Commit plan (2 commits, atomic rename+packaging)

1. `rebrand: pyvim -> vith (package, entries, markers, identity strings, license stack, PEP 621, README.md)` — W1+W2+W3+W4+W5 with gates (single atomic commit so no intermediate `import pyvim` breakage),
2. `docs: rename-all across OKF bundles; CHANGELOG 1.0.0 preamble + pyvim-history appendix` — W6+W7.

## 5. Open decisions at execution

| Decision | Recommendation | Alternatives |
|---|---|---|
| User-data migration | graceful fallback to `~/.pyvim*` | hard cutover / keep legacy paths |
| Version lineage | reset to `1.0.0` | continue 4.x (upgrade-path safe), or start 0.x |
| mypy config location | keep `mypy.ini` as-is | fold into `pyproject` `[tool.mypy]` |
| PyPI registration | manual step on the owner's account (`vith` slot re-check via PyPI JSON API at execution) | — |

[^src]: package tree, `setup.py`, `README.rst`, `CHANGELOG`, `docs/` — all anchors listed inline above. History cited by Mercurial node id (§0); rev numbers are hg-git-local and never used.
