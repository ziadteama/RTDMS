# rtdms-distraction

Driver distraction from an **infrared cabin camera at the centre mirror** (Raspberry Pi 5 + 160°
NoIR camera). It also runs on a PC with a video file or a webcam.

| Behaviour | How it is detected (default `simple` mode) |
|---|---|
| `phone` | a phone box in ≥ 60 % of the last second → **ALERT** |
| `phone_in_hand` | head ≥ 15° down from the driver's own baseline + a wrist low and central (pose model) → **WARNING** after 2 s, **ALERT** after 3 s (texting with the phone out of view) |
| `drinking` | a drink box over the lower face for 0.5 s → **ALERT** |
| `eating` | a food box over the lower face → ALERT (**not reliable**: food is rarely visible) |

One small detector (**YOLO26n**, trained on gray / IR images) finds phone, drink and food boxes; the
face mesh (shared with `models/face`) gives the lower-face zone and head pose; YOLO26n-pose gives the
wrists. **The trained models are in git** ([models/README.md](models/README.md): which file to use,
results, checksums), so a fresh clone runs straight away.

**Where things stand (2026-10-19):** on 10 unseen SynDD drivers, 80–100 % of phone calls and 90 % of
drinks raise an alert, with 0 phone false alarms per hour. On cameras it never saw, phones are still
found, but false alarms depend on where the camera sits (up to 69 per hour on a close-up camera that
sees the steering wheel large). Eating is not supported. Full story:
[docs/OVERNIGHT_REPORT.md](docs/OVERNIGHT_REPORT.md).

```
camera frame (gray) → driver area (fisheye rectified, or a crop) → YOLO26n 512 px (NCNN)
                    → face mesh (MediaPipe)  → YOLO26n-pose 320 px (every 3rd frame)
                    → rules (seconds, face-width units, per-drive baseline) → ALERT / WARNING
                    → overlay + JSONL event log
```

## Quick start on a PC (Windows, Linux or macOS, Python 3.11+)

```bash
git clone https://github.com/ziadteama/RTDMS.git
cd RTDMS
git checkout phone/distraction-baseline        # until this branch is merged into main
cd models/distraction
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux / macOS: source .venv/bin/activate
pip install -e ".[mediapipe,ncnn,dev]"
python -m pytest                               # ~120 tests, no camera or network needed
```

Run it:

```bash
# a recorded video (IR or colour); a source without a fisheye lens needs --no-rectify
python scripts/run.py --video my_clip.mp4 --no-rectify --roi full
# headless, events only (what the Pi does)
python scripts/run.py --video my_clip.mp4 --no-rectify --roi full --no-display --log-dir logs
# the laptop webcam
python scripts/live.py
```

`live.py` keys: `q` quit, `r` redo the head-pose baseline, `g` gray on / off (the model is trained on
gray images: keep it on for a colour webcam), `m` next model, `[` / `]` lower / raise the threshold,
`d` debug overlay.

Events go to `logs/drive_*.jsonl` (one line per start, level change and end). The first ~10 s with a
face are the per-drive head-pose baseline: sit normally, eyes on the road.

`ncnn` pulls `opencv-python` and `mediapipe` pulls `opencv-contrib-python`; they share the `cv2`
folder. If `import cv2` breaks after an upgrade, reinstall both at the same version.

## Raspberry Pi 5 (Raspberry Pi OS, aarch64)

```bash
git clone https://github.com/ziadteama/RTDMS.git && cd RTDMS && git checkout phone/distraction-baseline
cd models/distraction && bash scripts/install_pi.sh   # venv (picamera2 from apt) + MediaPipe + ncnn
```

Bring-up on the car, once per camera mount:

```bash
# 1. fisheye intrinsics: print a 9x6 checkerboard, measure the square size
python scripts/calibrate_fisheye.py --headless --views 25 --pattern 9x6 --square 0.025 --save-views data/calib
# 2. driver area: grab a frame, then draw a box around head, both ears, hands, lap and wheel rim
python scripts/select_roi.py --grab data/cabin.png
python scripts/select_roi.py --image data/cabin.png
# 3. run (events -> logs/drive_*.jsonl) and measure the speed with everything on
python scripts/run.py --no-display
python scripts/bench.py --duration 60 --json bench_pi.json
```

Faster detector on the Pi: set `detector.weights: models/det_v2d_ir_512_det_aciq_mixed_ncnn_model`
in `configs/pipeline.yaml` (INT8, same accuracy within noise). Alternative worth trying on the real
fisheye camera: `models/det_v2h_fish_512_ncnn_model` with thresholds phone 0.35 / drink 0.55.

## Configuration

| File | What it holds |
|---|---|
| `configs/pipeline.yaml` | camera, driver side, ROI, rectification, **detector weights + thresholds**, face mesh, pose, logging |
| `configs/rules.yaml` | `mode: simple` (default) or `full` (older engine: hands, ear zones, crop classifiers); every timing and distance |
| `configs/profiles/laptop_webcam.yaml` | overrides for `live.py` on a laptop (the model list for the `m` key) |
| `configs/data.yaml` | where training data lives (`root`, default `D:/rtdms-data`) |
| `configs/syndd_split.json` | the fixed SynDD driver split (49 train / 10 validation / 10 test) |

`left` / `right` always mean the **driver's** ears; `driver_side: right` = left-hand-drive car. Never
mirror the input (selfie view): it swaps the ears.

## Layout

```
configs/      settings (table above)
src/rtdms_distraction/   capture, calibration, roi, detector, facemesh, pose, hands, simple_rules,
                         rules, smoothing, pipeline, viz, eventlog, datasets, training, config
scripts/      run.py (Pi / video), live.py (webcam), bench.py, calibrate_fisheye.py, select_roi.py
              data:   fetch_syndd.py, build_openimages.py, label_video_boxes.py, build_det_v2.py
              train:  train.py   export: export_ncnn.py, quantize_int8.py
              eval:   eval_simple.py, eval_events.py, hand_check_sheets.py
experiments/  every experiment behind the report (unseen-data tests, cross-validation, rule
              tuning, SAM 2, fisheye, ...): see experiments/README.md
models/       shipped models (in git) + regenerated ones (git-ignored): see models/README.md
docs/         see below
tests/        unit tests (rules, smoothing, ROI, decoding, config, datasets, live tools)
```

## Documentation

| Document | Read it for |
|---|---|
| [models/README.md](models/README.md) | the shipped models: which to use, results, speed, checksums, licences |
| [docs/REPRODUCE.md](docs/REPRODUCE.md) | **rebuilding everything**: datasets → labels → training → export → INT8 → evaluation |
| [docs/OVERNIGHT_REPORT.md](docs/OVERNIGHT_REPORT.md) | every experiment and its numbers in plain English: what helped, what did not |
| [experiments/README.md](experiments/README.md) | the scripts behind each experiment and how to run them |
| [docs/DETECTOR_V2.md](docs/DETECTOR_V2.md) | how the detector's training set was built |
| [docs/DATA.md](docs/DATA.md) | datasets, licences, class mapping |
| [docs/IN_CAR_TEST_PROTOCOL.md](docs/IN_CAR_TEST_PROTOCOL.md) | recording volunteers in the car (the deciding test) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | design, contracts, failure policy |
| [docs/EVIDENCE.md](docs/EVIDENCE.md), [docs/LAPTOP_TESTING.md](docs/LAPTOP_TESTING.md) | earlier measurements and the webcam test |

## Evaluate a model

```bash
# alert-level test on the 10 held-out SynDD drivers (needs the SynDD videos: docs/REPRODUCE.md)
pip install -e ".[train]"
python scripts/eval_simple.py --split test --models det_v2d=models/det_v2d_ir_512.pt@512 \
    --class-conf phone=0.40,drink=0.45,food=0.40 --out reports/eval_test
```

## Verify

```bash
python -m pytest && python -m ruff check src tests scripts
docker compose run --rm verify          # canonical; needs Docker Desktop running
```
