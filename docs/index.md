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
  at: "2026-11-05T17:38:00Z"
timestamp: 2026-11-05T17:38:00Z
---

# pyvim Documentation Bundle

This directory contains the [Open Knowledge Format (OKF v0.2)](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) documentation bundle for `pyvim`.

## Architecture & Design Plans

* [Thai & Lao Script Support Plan](thai_support_plan.md) — Root-cause analysis (`prompt_toolkit` vs `pyvim`), `O(1)` cell-cluster architecture adapted from `szn`, Vi motion/editing specifications, rendering coordinate fix, and test matrix.
* [Speed, Latency & Python 3.15 Stability Plan](speed_latency_plan.md) — Codebase-wide performance audit, Python 3.15 `asyncio.get_event_loop()` crash fix, and zero-`prompt_toolkit`-touch optimizations for startup time, incremental lexing, keystroke latency, and frame rendering.

## Meta

* [Bundle Update Log](log.md) — Chronological log of documentation bundle additions and updates.
