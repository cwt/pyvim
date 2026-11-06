---
type: log
title: "pyvim Findings Bundle Update Log"
description: "Chronological log of modifications to the docs/bugs/ OKF bundle."
status: stable
sources:
  - docs/bugs/
verified: machine-confirmed
generated:
  by: "OpenCode (GLM-5.3-Flash)"
  at: "2026-11-06T12:12:00Z"
timestamp: "2026-11-06T12:12:00Z"
---

# Findings Bundle Log

This file tracks all modifications to the `docs/bugs/` findings bundle in chronological order.

| Timestamp | Document | Action | Description |
| :--- | :--- | :--- | :--- |
| 2026-11-06T12:12:00Z | [index.md](index.md), [001.md](001.md)…[037.md](037.md) | Created | Established the `docs/bugs/` OKF v0.2 bundle with 37 machine-verified findings from the deep review at hg rev 164: 16 defects ([001](001.md)–[016](016.md)) and 21 improvements ([017](017.md)–[037](037.md)), each with evidence (measurements, probes, toolchain checks) and fix direction. Linked from the root [`../index.md`](../index.md) bundle. |
| 2026-11-06T13:00:00Z | [001.md](001.md)…[037.md](037.md), [index.md](index.md) | Updated / findings closed | **Resolution record:** the 2026-11-06 fix arc closed all 37 findings — defects 001 (rev 169), 002 (170), 003 (171), 004+015 (172), 005 (174), 006+007 (173), 008 (175), 009+014 (180), 010 (176), 011+012 (177), 013 (178), 016 (182); improvements 017–024 (183), 025+027+032 (188), 026 (189), 028 (185), 029 (186), 030 (184), 031 (190), 033 (192), 034 (193), plus tooling groundwork (167: pytest/mypy/ruff into the project venv, ruff config + codebase format). The closing changeset (rev 195) adds the CHANGELOG/README refresh and `requirements-dev.txt`. Final verification: 100+ tests pass, mypy clean at the 3.10 floor (43 files), ruff clean, `tools/bench_plans.py` reproduces the plan figures, perf probes: Thai `w` ~0.4 ms (was ~640 ms) and SARA-AM wrapper ~0.002 ms/frame on ASCII sessions (was ~1.3 ms). |
