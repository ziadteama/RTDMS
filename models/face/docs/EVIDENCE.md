# Face subsystem — evidence

What has actually been measured, on which environment. Update this file when a
gate in `VALIDATION.md` produces new numbers — do not leave stale figures in
README alone.

## Provenance of this snapshot

Imported from upstream `dms-face` README (commit `65e3afd`, 2026-08-28).
**Environment: development laptop, not the Pi.** Treat as a baseline to beat
or match on Pi 5, not as a deployment claim.

## G1 — Deterministic core

| When | Environment | Result |
|---|---|---|
| Upstream ship | local | 31+ unit tests in `tests/test_core.py` |
| Monorepo adoption | TBD — run `docker compose run --rm verify` and record here | |
| 2026-10-10, branch `face/pi-litert-stream` | Windows laptop, root `.venv`, Python 3.14 — **not** the Docker gate | 43 passed (`test_core.py` + new `test_litert.py`) |

## G4 — Fixed-image throughput (laptop baseline)

Command: `python bench.py --source image --resolutions`

Host: Intel, 32 cores, Python 3.14, mediapipe 1.0.1.

| Input resolution | FPS | Inference (mean) | CPU | RSS |
|---|---:|---:|---:|---:|
| 320×240 | 75.3 | 12.4 ms | 102% | 120 MB |
| 480×360 | 54.1 | 17.7 ms | 105% | 123 MB |
| 640×480 | 55.4 | 17.4 ms | 104% | 125 MB |
| 960×720 | 53.9 | 17.8 ms | 104% | 129 MB |

Observations already argued in upstream docs (keep when citing):

1. Resolution above ~480×360 buys nothing — MediaPipe resizes internally.
2. ~104% CPU ≈ one core; face landmarks do not by themselves justify the AI HAT+.

## G4 — Pi 5

Measured 2026-10-10 on the project Pi 5 (8 GB, Raspberry Pi OS trixie, kernel
6.18, Python 3.13), `litert` backend (`ai-edge-litert`, XNNPACK), camera OV5647
at 640×480 @ 30 fps. `vcgencmd get_throttled` = `0x0` throughout, SoC 48–51 °C.
**Standalone face process only** — this does not close G6.

Per-network latency, fixed image, median of 300 runs after warm-up:

| Network | 1 thread | 2 threads |
|---|---:|---:|
| `face_landmarks_detector` (478 pts, 256×256), tracking | 13.4 ms | 8.0 ms |
| `face_detector` (BlazeFace, 128×128), reacquire only | 5.0 ms | 3.7 ms |

Live, `stream.py` defaults (1 thread), driver in frame, one browser viewer:

| Metric | Value |
|---|---:|
| Pipeline FPS | 30.0 (camera-bound) |
| Mesh inference | 13.5 ms |
| Post-inference arithmetic (EAR → state) | 0.4 ms |
| Pipeline total | 14.1 ms of the 33 ms frame budget |
| HUD draw + JPEG (only with a viewer) | 4.3 ms |
| Process CPU | 73 % of one core |
| System CPU | ~21 % of four cores |
| RSS | 133 MB |

No face in view (detector every frame): 6.7 ms/frame, ~48 % of one core.

Open items: the same table for the ONNX path (`tflite2onnx` on the bundle);
G6 with phone + physiology live; the `mediapipe` backend on the Pi for an
apples-to-apples baseline.

## Camera intrinsics sensitivity (methodology)

Fixed frame, sweep assumed focal length only (upstream measurement):

| focal | yaw | pitch | roll |
|---:|---:|---:|---:|
| 400 | −1.4 | **38.1** | −1.4 |
| 820 | −1.6 | **21.1** | −1.0 |
| 2000 | −1.7 | **9.4** | −0.7 |
| 3000 | −1.7 | **6.5** | −0.6 |

Consequence implemented in code: distraction uses pitch relative to calibrated
neutral, never absolute pitch.

## Calibration SNR reference

One measured adult face (upstream): separation 0.2414, jitter 0.0035,
**SNR 69.7 — good**. Expand with volunteer distribution under G5.

## Environment caveats

- Laptop numbers ≠ Pi numbers.
- IR / night performance of MediaPipe is degraded vs RGB; measure on the IR
  module before claiming night accuracy.
- Concurrent load with physiology is unmeasured (G6 open).
