---
title: "Distraction Subsystem (IR Camera: Phone / Drink / Food)"
tags:
  - subsystem
  - implementation
  - vision
  - phone
  - distraction
aliases:
  - rtdms-distraction
  - distraction detection
  - IR distraction
status: release-models-shipped
code_path: models/distraction
language: Python 3.11+
owner: TBD
---

# Distraction Subsystem (IR Camera: Phone / Drink / Food)

↑ [[Home]] | Model index: [[Models Index]] | Target: [[Raspberry Pi 5 Target]]

Driver distraction from the **infrared cabin camera at the centre mirror** (Pi 5 + 160° NoIR
camera); also runs on a PC with a video file or webcam. One small detector (**YOLO26n**, trained
on gray / IR images) finds phone, drink and food boxes; the face mesh (shared with
[[Face Subsystem]]) gives the lower-face zone and head pose; YOLO26n-pose gives the wrists. Rules
in seconds and face-width units turn these into ALERT / WARNING events (JSONL log).

**Code:** `models/distraction/` — on branch `phone/distraction-baseline` until merged; release
models shipped 2026-10-19.

**Supersedes [[Phone Subsystem]] for the IR camera.** `models/phone/` (State Farm classifier) is
kept, not deleted.

Docs: [`README.md`](../models/distraction/README.md) ·
Model card: [`models/README.md`](../models/distraction/models/README.md) ·
Rebuild: [`docs/REPRODUCE.md`](../models/distraction/docs/REPRODUCE.md) ·
Experiments: [`docs/OVERNIGHT_REPORT.md`](../models/distraction/docs/OVERNIGHT_REPORT.md)

## What it detects (default `simple` mode)

| Behaviour | Rule |
|---|---|
| `phone` | phone box in ≥ 60 % of the last second → **ALERT** |
| `phone_in_hand` | head ≥ 15° down from the driver's baseline + a wrist low and central → **WARNING** after 2 s, **ALERT** after 3 s |
| `drinking` | drink box over the lower face for 0.5 s → **ALERT** |
| `eating` | food box over the lower face → ALERT (**not reliable**: food is rarely visible) |

## Shipped models (in git)

| File | Use |
|---|---|
| `det_v2d_ir_512_ncnn_model/` | **Default** detector, FP32 NCNN, 512 px (PC and Pi) |
| `det_v2d_ir_512_det_aciq_mixed_ncnn_model/` | Same model, INT8 mixed (2.8 MB, ~20 % faster on Pi, same accuracy within noise) |
| `det_v2d_ir_512.onnx` / `det_v2d_ir_512.pt` | ONNX (Hailo DFC input) / PyTorch weights |
| `det_v2h_fish_512_ncnn_model/` | Fisheye-tuned alternative for the real Pi camera (phone 0.35, drink 0.55) |
| `yolo26n_pose_320_ncnn_model/` | Wrist keypoints for the texting rule |

Thresholds (tuned on 10 validation drivers): phone 0.40, drink 0.45, food 0.40.

## Key results (alert level, 10 FPS)

| Test | Phone right ear | Phone left ear | Texting | Drinking | Phone false alarms |
|---|---|---|---|---|---|
| SynDD test, 10 unseen drivers | 80 % | 100 % | 41.5 % (46 % with warnings) | 90 % | 0 / h |
| 5-fold by driver, 59 drivers (mean) | 89 % | 97 % | 65 % | 66 % | 9.0 / h |
| 3MDAD, 50 unseen drivers | 80 % | 92 % | 96 % right hand / 16 % left | 68–80 % | 8 % of normal clips |
| DAD, 3 unseen drivers, real IR | 4 / 5 calls | | 5 / 6 | 2 / 2 | **69 / h** |

Eating: 0 % everywhere — unsupported. False alarms depend strongly on camera position.
Speed (laptop CPU, NCNN, 4 threads): FP32 28.3 ms, INT8 22.6 ms per frame.

## Status

| Item | State |
|---|---|
| Detector + rules + tests | **Done** |
| Release models in git (FP32 / INT8 / ONNX / pose) | **Done** (2026-10-19) |
| Pi 5 concurrent bench | Open |
| In-car volunteer recording | Open (`docs/IN_CAR_TEST_PROTOCOL.md`) |
| Eating | Unsupported |

## Ownership

Branch zone `phone/<topic>`. See `models/README.md` and `.cursor/rules/git-branching.mdc`.
