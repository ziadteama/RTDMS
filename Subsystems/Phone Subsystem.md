---
title: "Phone Subsystem (Phone / Eating Distraction)"
tags:
  - subsystem
  - implementation
  - vision
  - phone
  - distraction
aliases:
  - dms-phone
  - phone detection
  - eating distraction
status: implemented-onnx
code_path: models/phone
language: Python 3.11+
owner: TBD
---

# Phone Subsystem (Phone / Eating Distraction)

↑ [[Home]] | Model index: [[Models Index]] | Target: [[Raspberry Pi 5 Target]]

Cabin **manual distraction** model: multi-class `{safe, phone, eating}` for fusion.
Pi-first ONNX at ~5 Hz. Does not merge with [[Face Subsystem]] or [[Physiology Subsystem]].

**Code:** `models/phone/` — scaffolded 2026-09-20; **ONNX wired 2026-09-25** from open
Safe-Drive-TN State Farm weights (no local train).

Contracts: [`models/phone/docs/ARCHITECTURE.md`](../models/phone/docs/ARCHITECTURE.md) ·
Validation: [`VALIDATION.md`](../models/phone/docs/VALIDATION.md) ·
Evidence: [`EVIDENCE.md`](../models/phone/docs/EVIDENCE.md)

## Why separate from face

Face owns EAR/PERCLOS/gaze from MediaPipe. Phone/eating need whole-cabin appearance
(side-door mount). Shared **capture**, separate **inference**, fusion combines scores.

## Pi priority

`.cursor/rules/pi-performance-pipeline.mdc` — concurrent budget beats laptop DX.

## Status

| Item | State |
|---|---|
| Package + OutputSink + tests | **Done** |
| Ready weights → `phone_cls.onnx` + 10→3 collapse | **Done** (Safe-Drive-TN) |
| Hold-out phone ≥85% measurement | Open (optional State Farm val later) |
| Pi concurrent bench | Open |
| Live camera | Blocked — no camera on Pi |
| AUC | **Deferred** |

## Ownership

Branch zone `phone/<topic>`. See `models/README.md` and `.cursor/rules/git-branching.mdc`.
