# Validation gates

A release of this module is gated on the evidence below, recorded in EVIDENCE.md with the
environment it was measured on. Numbers produced only on the laptop are labelled as such until
repeated on the Pi.

## Gate 0 — code (every change)

- `pytest` and `ruff check src tests scripts` green (Docker `verify` is canonical).
- `scripts/check_detector_parity.py`: NCNN and ONNX decode match Ultralytics on the same export
  (IoU ≥ 0.99, |Δconf| ≤ 0.01) whenever the detector, letterbox or decode changes.

## Gate 1 — rig bring-up (once per camera / mount)

- Fisheye calibration RMS ≤ 1.0 px over ≥ 20 views covering the frame edges.
- `select_roi.py --preview` shows the driver's head, both ears, hands, lap and wheel rim, with
  straight lines straight; no passenger seat inside the view (or masked).
- Pose sign check on the real rig: nod down → pitch increases; turn toward image-right → yaw
  increases (synthetic + still-image checks exist; a live check does not yet).

## Gate 2 — detector (Phase 3/4)

- mAP50 and per-class AP on held-out **subjects** (no person in two splits), reported for day
  and night separately, phone / drink / food / hand.

## Gate 3 — system (Phase 4)

Per behaviour, event level, on: own test set, SynDD rear-view, YawDD negatives, DMD night.

- Precision / recall / F1 (an event counts as detected if the alert overlaps the labelled span).
- False alarms per hour of normal driving (YawDD talking/singing must not trigger eating).
- Time-to-alert from labelled onset (median, p90). Phone target: within the RTDMS 1 s budget
  after the smoothing window; document the window's share of it.

## Gate 4 — Pi

- ≥ 10 FPS end-to-end on the Pi 5 CPU, sustained over 30 min (`bench.py --duration 1800`),
  with CPU temperature logged and `vcgencmd get_throttled` = 0x0 before and after. Any non-zero
  throttle flag invalidates that run.
- If < 10 FPS: rerun with `--detect-every 2` and report both.
- Repeat concurrently with models/face and physiology running (repo rule: standalone numbers are
  not budget evidence).
