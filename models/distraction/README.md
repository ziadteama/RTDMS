# rtdms-distraction

Driver distraction from the mirror-mounted fisheye IR cabin camera, on a Raspberry Pi 5 CPU:

| Behaviour | Evidence |
|---|---|
| `phone_right_ear` | phone box in a zone beside landmark 234 (driver's right ear) |
| `phone_left_ear` | phone box (possibly partial) **or a hand** beside / behind landmark 454 |
| `phone_in_hand` | phone below the face, next to a hand, not in a holder → WARNING; head/gaze down > 2 s → ALERT |
| `drinking` | drink box over the mouth region; head tilted back raises confidence |
| `eating` | food at the mouth in the last 5 s **and** chewing (jaw at 0.8–2.5 Hz, lips mostly closed) |

`left`/`right` are the **driver's** ears. Which ear is the "far", partly hidden one follows
`driver_side` (right = left-hand-drive car). Design, contracts and failure policy:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). What has actually been measured:
[docs/EVIDENCE.md](docs/EVIDENCE.md).

```
frame 1296x972 gray → rectify driver ROI (fisheye → virtual pinhole) → YOLO26n (NCNN, 416)
                                                                    → face mesh on a face crop
                                                                    → MediaPipe hands (baseline)
                    → rules (face-size units, per-drive baseline) → sliding window + hysteresis
                    → per-frame states + JSONL event log (+ debug overlay)
```

## Layout

```
configs/pipeline.yaml   capture, driver_side, ROI, rectification, detector, face mesh, hands, log
configs/rules.yaml      every behaviour threshold, smoothing, levels
src/rtdms_distraction/  capture  calibration  roi  detector  hands  facemesh  rules  smoothing
                        pipeline  viz  eventlog  config  types
scripts/                run, bench, calibrate_fisheye, select_roi, export_ncnn,
                        check_detector_parity, fetch_models, install_pi.sh
tests/                  rules / smoothing / ROI / decode / config / pose / pipeline (no camera, no NN)
models/                 weights (gitignored; regenerate with the scripts)
data/  logs/            recordings and event logs (gitignored)
```

The face landmarker bundle is shared with `models/face/models/face_landmarker.task`.

## Environments

### PC: development + training (x86-64, NVIDIA GPU)

```bash
py -3.14 -m venv ../../../venvs/rtdms-train          # any location; outside the repo
../../../venvs/rtdms-train/Scripts/python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
../../../venvs/rtdms-train/Scripts/python -m pip install -e ".[train,mediapipe,ncnn,onnx,bench,dev]"
python scripts/fetch_models.py                        # hand_landmarker.task
python scripts/export_ncnn.py --onnx                  # yolo26n.pt -> NCNN + ONNX at imgsz 416
python scripts/check_detector_parity.py --images some.jpg --pt models/yolo26n_coco_416.onnx
```

`ncnn` pulls `opencv-python` and `mediapipe` pulls `opencv-contrib-python`; they share the `cv2`
folder and work together only at the same version. If `import cv2` breaks after an upgrade,
reinstall both at one version.

### Raspberry Pi 5 (aarch64, Raspberry Pi OS)

```bash
cd models/distraction && bash scripts/install_pi.sh
```

The venv is created with `--system-site-packages` (picamera2 comes from apt). Runtime only:
MediaPipe + `ncnn` + OpenCV, no PyTorch. Copy `models/yolo26n_coco_416_ncnn_model/` from the PC.
MediaPipe ships `py3-none-manylinux_2_28_aarch64` wheels from 1.0 on, so Bookworm (3.11) and Trixie
(3.13) both work; the fallback if that ever changes is in the script header.

## Bring-up on the car

```bash
# 1. Fisheye intrinsics (print a checkerboard; 9x6 inner corners, measure the square size)
python scripts/calibrate_fisheye.py --headless --views 25 --pattern 9x6 --square 0.025 --save-views data/calib
# 2. Driver ROI (grab a frame on the Pi, draw on a PC, or pass numbers)
python scripts/select_roi.py --grab data/cabin.png
python scripts/select_roi.py --image data/cabin.png                          # draw; saves roi.rect
python scripts/select_roi.py --image data/cabin.png --rect 820,120,420,560 --preview roi.png
# 3. Run
python scripts/run.py --no-display                 # events -> logs/drive_*.jsonl
python scripts/bench.py --duration 60 --json bench_pi.json
```

The first ~10 s with a face is the per-drive head-pose baseline: sit normally, eyes on the road.

## Running on recordings and public datasets

```bash
python scripts/run.py --video clip.mp4 --save-video overlay.mp4 --no-display
# Non-fisheye sources (laptop webcam, SynDD rear-view, YawDD mirror, DMD): no rectification
python scripts/run.py --video syndd_rear.mp4 --no-rectify --roi full --driver-side right
```

Keys in the overlay window: `q`/`Esc` quit, `space` pause, `b` restart the baseline.
Never mirror the input (webcam "selfie" views): mirroring swaps the driver's ears.

## Training data and evaluation

The detector is fine-tuned on **public data only** (Open Images now; SynDD, 100-Driver, DMD and
YawDD as they arrive), converted to look like our camera. Our own clips are test data. Details,
sources, licences, teacher labelling and caveats: [docs/DATA.md](docs/DATA.md). One-time in-car
test session: [docs/IN_CAR_TEST_PROTOCOL.md](docs/IN_CAR_TEST_PROTOCOL.md).

```bash
python scripts/build_openimages.py                     # download + balanced subset (D:/rtdms-data)
PY=python bash scripts/run_oiv_pipeline.sh v1          # teacher -> convert -> train 416/512 -> eval
python scripts/review_sample.py make --labels <root>/openimages/labels_meta/train \
    --images <root>/openimages/images/train            # label-quality review page
python scripts/eval_events.py s01 --src data/recordings/S01_guided_<utc>.mp4 --weights <ncnn dir>
```

## Verify

```bash
python -m pytest && python -m ruff check src tests scripts
docker compose run --rm verify          # canonical; needs Docker Desktop running
```
