---
type: index
title: "pyvim Documentation Bundle"
description: "OKF v0.2 knowledge bundle root for the pyvim project."
status: stable
sources:
  - docs/
verified: machine-confirmed
generated:
  by: "Agnes (Sapiens AI)"
  at: "2026-11-06T07:30:00Z"
timestamp: 2026-11-06T07:30:00Z
---

# pyvim Documentation Bundle

This directory contains the [Open Knowledge Format (OKF v0.2)](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) documentation bundle for `pyvim`.

## Architecture & Design Plans

* [Thai & Lao Script Support Plan](thai_support_plan.md) — Root-cause analysis (`prompt_toolkit` vs `pyvim`), cell-cluster vs syllable granularity, `SARA AM` (`U+0E33`/`U+0EB3`) differential renderer neighbor refresh (ported from `szn` `71ba808`), version-gated `prompt_toolkit` integration, and test matrix.
* [Speed, Latency & Python 3.15 Stability Plan](speed_latency_plan.md) — **Implemented (rev 161–162)**: reproducible Python 3.15.2 benchmarks ([`../tools/bench_plans.py`](../tools/bench_plans.py)), Python 3.14+ `asyncio.get_event_loop()` startup crash fix, streaming/cached `PygmentsLexer`, lazy colorscheme loading, singleton word completion caching (incl. jedi 0.20 dual-API support), O(1) error line index, `io.open` & dirty-flag cleanups, mypy baseline ([`../mypy.ini`](../mypy.ini)); deviations & follow-ups logged in §1.4.

## Meta

* [Bundle Update Log](log.md) — Chronological log of documentation bundle additions and updates.
