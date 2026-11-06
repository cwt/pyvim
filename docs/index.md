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
  at: "2026-11-06T08:00:00Z"
timestamp: "2026-11-06T08:00:00Z"
---

# pyvim Documentation Bundle

This directory contains the [Open Knowledge Format (OKF v0.2)](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) documentation bundle for `pyvim`.

## Architecture & Design Plans

* [Vith Re-brand & Modernization Plan](vith_rebrand_plan.md) — **Queued (execution planned 2026-11-week 46+)**: new identity `vith` (วิธ) breaking the fork naming,	BSD 3-clause kept with stacked copyright, `setup.py` → `pyproject.toml` (PEP 621), `README.rst` → `README.md`, user-data migration with graceful fallback, docs sweep and gate re-verification. Three open decisions recorded at §5.
* [Thai & Lao Script Support Plan](thai_support_plan.md) — **Implemented**: root-cause analysis (`prompt_toolkit` vs `pyvim`), cell-cluster vs syllable granularity ([`../pyvim/thai.py`](../pyvim/thai.py), [`../pyvim/key_bindings.py`](../pyvim/key_bindings.py)), `SARA AM` (`U+0E33`/`U+0EB3`) differential renderer neighbor refresh (ported from `szn` `71ba808`), version-gated `prompt_toolkit` integration, and unit test suite ([`../tests/test_thai.py`](../tests/test_thai.py)).
* [Speed, Latency & Python 3.15 Stability Plan](speed_latency_plan.md) — **Implemented (rev 161–162)**: reproducible Python 3.15.2 benchmarks ([`../tools/bench_plans.py`](../tools/bench_plans.py)), Python 3.14+ `asyncio.get_event_loop()` startup crash fix, streaming/cached `PygmentsLexer`, lazy colorscheme loading, singleton word completion caching (incl. jedi 0.20 dual-API support), O(1) error line index, `io.open` & dirty-flag cleanups, mypy baseline ([`../mypy.ini`](../mypy.ini)); deviations & follow-ups logged in §1.4.

## Audit & Findings

* [Findings Bundle](bugs/index.md) — **Closed (2026-11-06)**: 37 machine-verified findings from the deep review at hg rev 164 — defects 001–016 (`type: bug`, incl. two high-priority performance findings in the Thai hot paths and several uncaught-exception paths) and improvements 017–037 (`type: improvement`: dead code, duplication, legacy weight, packaging/toolchain, readability, docs drift). All fixed during the 2026-11-06 fix arc; every doc records its fix revision.

## Meta

* [Bundle Update Log](log.md) — Chronological log of documentation bundle additions and updates.
