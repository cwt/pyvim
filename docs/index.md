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
  at: "2026-11-05T18:05:00Z"
timestamp: 2026-11-05T18:05:00Z
---

# pyvim Documentation Bundle

This directory contains the [Open Knowledge Format (OKF v0.2)](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) documentation bundle for `pyvim`.

## Architecture & Design Plans

* [Thai & Lao Script Support Plan](thai_support_plan.md) — Root-cause analysis (`prompt_toolkit` vs `pyvim`), cell-cluster vs syllable granularity, `SARA AM` (`U+0E33`/`U+0EB3`) differential renderer neighbor refresh (ported from `szn` `71ba808`), version-gated `prompt_toolkit` integration, and test matrix.
* [Speed, Latency & Python 3.15 Stability Plan](speed_latency_plan.md) — Reproducible Python 3.15.2 benchmarks ([`../tools/bench_plans.py`](../tools/bench_plans.py)), Python 3.14+ `asyncio.get_event_loop()` startup crash fix, streaming/cached `PygmentsLexer`, lazy colorscheme loading, and singleton word completion caching.

## Meta

* [Bundle Update Log](log.md) — Chronological log of documentation bundle additions and updates.
