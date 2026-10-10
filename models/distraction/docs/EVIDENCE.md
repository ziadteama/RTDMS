# Evidence

What has actually been measured, where, and what has not. Phase 0 + Phase 1, 2026-10-10.

> [!warning] No Pi numbers yet
> The Pi 5 was unreachable on both its Tailscale and LAN addresses during this session. Every
> timing below is from the development laptop and is **not** budget evidence (repo rule: Pi,
> concurrent). The laptop numbers only show the stage *proportions* and that the path runs.

## Environment

| | |
|---|---|
| Machine | Windows 11 laptop, Intel Core i9-14900HX, RTX 4060 Laptop (training only) |
| Python | 3.14.4 |
| Packages | opencv 5.0.0, numpy 2.5, mediapipe 1.1.0, ncnn 1.0.20260526, onnxruntime 1.31.0, ultralytics 8.4.175, torch 2.14.1+cu130 |
| Detector | `yolo26n.pt` (COCO) exported at imgsz 416 → NCNN (9.7 MB) and ONNX (9.8 MB) |

## Gate 0 — code

- `pytest`: **64 passed**, both in the full training env and in a bare venv with only
  numpy / opencv / pyyaml / pytest (so Docker `verify` needs no neural runtimes).
  `ruff check src tests scripts`: clean. Docker `verify` itself **not run** (Docker Desktop was
  not running).
- Rules covered with synthetic landmarks and boxes: both ears for both `driver_side` values,
  hand-only far-ear evidence and its two guards (hand at the mouth, hand holding a cup), phone in
  hand with / without hands, holder zones, drinking + pitch-up bonus, eating vs chewing-without-
  food vs talking vs singing vs still mouth, food memory expiry, geometric jaw source, face lost.
- End-to-end timing with fake detector/face (`test_pipeline.py`): phone-in-hand onset at 2.0 s →
  WARNING at 2.9–3.3 s, head down from 4.0 s → ALERT at 5.9–6.2 s, face lost 7.0–7.5 s → state
  held, then de-escalates and ends. Event log: start → level → level → end.
- Fisheye maths (`test_roi.py`, synthetic equidistant lens, f = 465 px at 1296x972):
  raw → view → raw round trip < 0.05 px; a straight 3D line bent > 5 px in the raw image is
  < 0.5 px from straight in the driver view; `cv2.remap` output lands where `from_raw()` says
  (< 1 px); `cv2.fisheye.calibrate` on 25 synthetic board views recovers K (RMS < 0.01 px).

## Detector parity (`check_detector_parity.py`)

Ultralytics' own predictor on the exported ONNX vs our letterbox + decode on NCNN and ONNX,
`bus.jpg` + `zidane.jpg`, all 80 COCO classes, colour and grayscale×3:
**30/30 boxes matched, IoU ≥ 0.999, |Δconf| ≤ 0.002**.

> [!note] Methodology correction
> The first comparison used the `.pt` model as reference and showed |Δconf| up to 0.136 and
> 2 unmatched boxes. Cause: Ultralytics' PyTorch predictor letterboxes to a minimal stride-aligned
> rectangle (e.g. 416x320), while exported models get the fixed 416x416 square. Same weights,
> different input. The reference must be the export itself. Consequence: the `ultralytics`
> backend with a `.pt` file sees slightly different input than the Pi's NCNN; use `ncnn` on the
> PC too when comparing against Pi behaviour.

The NCNN/ONNX exports from Ultralytics 8.4.175 contain the raw one-to-many head
(84 x 3549 at 416), not YOLO26's NMS-free end-to-end head; decode applies class-wise NMS.

## Face mesh on a crop vs the whole view

Portrait (`models/face/tests/assets/portrait.jpg`) pasted into a 640x640 driver view at several
sizes, 90 frames each with slight motion, MediaPipe Face Landmarker:

| Face width in view | Whole view | Face crop (tiled search + tracking) |
|---|---|---|
| ~95 px | 90/90 | 87/90 |
| ~66 px | **0/90** | 87/90 |
| ~53 px | 0/90 | 88/90 |
| ~42 px | 0/90 | 88/90 |
| ~32 px | 0/90 | 0/90 |

The 2–3 misses with the crop are tile-search acquisition frames. The expected driver face at
this mount is ~90–110 px; the crop buys margin for smaller drivers, a farther seat and a
wider ROI. A still image says nothing about IR, glasses or real motion.

## Head pose sign check

- Synthetic: solvePnP on the canonical model projected with known pitch/yaw recovers them within
  1° for 6 poses including combined ones; head down moves the nose down in the image.
- Real still (portrait, colour and gray, original and mirrored): MediaPipe-matrix yaw and
  solvePnP yaw agree in sign and flip under mirroring. Absolute pitch differs (matrix ~4°,
  solvePnP ~21° with the focal ≈ width guess), the documented focal-guess bias that the
  baseline subtraction cancels.
- Found and fixed: unseeded `SOLVEPNP_ITERATIVE` converged to the mirrored solution behind the
  camera on the grayscale portrait; cold starts now use `SOLVEPNP_SQPNP`.
- **Not done:** a live nod / turn on a real person. Required before trusting pitch-down rules.

## Laptop timing (standalone, not Pi, not concurrent)

`bench.py`, synthetic 1296x972 clip, rectification ON (synthetic calibration), ROI 480x600 →
640x640 view, NCNN 2 threads, MediaPipe face + hands (hands every 2nd frame), 770 frames:

| Stage | mean ms | p95 ms |
|---|---|---|
| capture (video decode) | 3.3 | 5.6 |
| rectify (remap + gray→3ch) | 1.5 | 2.6 |
| detect (YOLO26n NCNN 416) | 30.4 | 47.5 |
| face mesh (crop 256) | 8.6 | 15.1 |
| hands (amortised) | 5.8 | 18.6 |
| rules + smoothing | 0.3 | 0.7 |
| **pipeline** | **46.5** | 76.3 |

End-to-end **19.9 FPS** on the laptop. The detector is ~65 % of the frame; `detector.every_n: 2`
is the first lever if the Pi misses 10 FPS.

## Not measured yet

- Anything on the Pi 5 (FPS per stage, temperature, throttling, 30 min soak).
- Real fisheye calibration of the OV5647 160° module; a real driver ROI.
- Any real driving behaviour: no recordings with this mount exist yet (Phase 2). Rule thresholds
  are engineering defaults, not tuned values.
- COCO detector recall on this camera, in grayscale and under IR. COCO "cell phone" in a hand at
  the ear, partly occluded, is expected to be weak; that is what Phase 3 fine-tuning is for.
- MediaPipe hands on small IR hands at this mount (the palm detector may miss hands < ~30 px).
- The `dms_face` LiteRT backend path through this package (adapter written, not executed: the
  LiteRT backend lives on the unmerged `face/pi-litert-stream` branch).
