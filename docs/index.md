---
type: index
title: "pyvim Documentation Bundle"
description: "OKF v0.2 knowledge bundle root for the pyvim project."
status: stable
sources:
  - docs/
verified: machine-confirmed
generated:
  by: "Antigravity (Gemini 4 Argon)"
  at: "2026-11-07T07:28:00Z"
timestamp: "2026-11-07T07:28:00Z"
---

# pyvim Documentation Bundle

This directory contains the [Open Knowledge Format (OKF v0.2)](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) documentation bundle for `pyvim`.

## Architecture & Design Plans

* [Vith Re-brand & Modernization Plan](vith_rebrand_plan.md) — **Queued (execution planned 2026-11-week 46+)**: new identity `vith` (วิธ) breaking the fork naming,	BSD 3-clause kept with stacked copyright, `setup.py` → `pyproject.toml` (PEP 621), `README.rst` → `README.md`, user-data migration with graceful fallback, docs sweep and gate re-verification. Three open decisions recorded at §5.
* [Thai & Lao Script Support Plan](thai_support_plan.md) — **Implemented**: root-cause analysis (`prompt_toolkit` vs `pyvim`), cell-cluster vs syllable granularity ([`../pyvim/thai.py`](../pyvim/thai.py), [`../pyvim/key_bindings.py`](../pyvim/key_bindings.py)), `SARA AM` (`U+0E33`/`U+0EB3`) differential renderer neighbor refresh (ported from `szn` `71ba808`), version-gated `prompt_toolkit` integration, and unit test suite ([`../tests/test_thai.py`](../tests/test_thai.py)).
* [Speed, Latency & Python 3.15 Stability Plan](speed_latency_plan.md) — **Implemented (rev 161–162)**: reproducible Python 3.15.2 benchmarks ([`../tools/bench_plans.py`](../tools/bench_plans.py)), Python 3.14+ `asyncio.get_event_loop()` startup crash fix, streaming/cached `PygmentsLexer`, lazy colorscheme loading, singleton word completion caching (incl. jedi 0.20 dual-API support), O(1) error line index, `io.open` & dirty-flag cleanups, mypy baseline ([`../mypy.ini`](../mypy.ini)); deviations & follow-ups logged in §1.4.

## Audit & Findings

* [Findings Bundle](bugs/index.md) — **61 findings across 2 audit rounds**:
  * **Round 2 (2026-11-07, hg rev 191 — open)**: 24 machine-verified findings ([038](bugs/038.md)–[061](bugs/061.md)) — 17 defects (`type: bug`, including 7 high-priority crashes and Thai/Lao Visual mode, inclusive motion, and word-completion bugs) and 7 improvements (`type: improvement`: performance, dead code, duplication, readability/test hygiene, and plan/benchmark drift).
  * **Round 1 (2026-11-06, hg rev 164 — closed in rev 167–195)**: 37 machine-verified findings ([001](bugs/001.md)–[037](bugs/037.md)) — defects 001–016 and improvements 017–037, all fixed with recorded hg revisions.

## Meta

* [Bundle Update Log](log.md) — Chronological log of documentation bundle additions and updates.
