# Face subsystem — Real-Time Driver Monitoring System

Eye closure, blink classification, PERCLOS, gaze and head pose from **one**
neural network inference per frame. Everything downstream is arithmetic.

Lives in the RTDMS monorepo as `models/face/`. Adopted from
[`youssefmedhat4/dms-face`](https://github.com/youssefmedhat4/dms-face) commit
`65e3afd` (2026-08-28). Full design rationale:
[`docs/UPSTREAM_README.md`](docs/UPSTREAM_README.md). Contracts:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Quick start

```bash
cd models/face
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# Linux/Pi: source .venv/bin/activate
pip install -e ".[dev,bench]"
pytest                          # deterministic core suite, no camera
python run.py --calibrate       # calibrate, then run live
```

On the Raspberry Pi (from this directory):

```bash
./install_pi.sh
```

Docker (canonical verify gate, mirrors physiology):

```bash
docker compose run --rm verify
```

## Scope in the monorepo

| This package covers | Still separate |
|---|---|
| EAR / openness / blink FSM | Phone-usage detection (`models/phone/` — not yet created) |
| PERCLOS (P80) | Physiology (`models/physiology/`) |
| Gaze deviation + head pose | DMS decision fusion + production alerts (Phase 4) |

Report §3.1 listed "drowsiness" and "distraction" as two vision models. This
package implements both camera channels that share one MediaPipe inference;
phone classification remains its own model so YOLO work does not collide with
face work.

## Ownership (parallel work)

See [`models/README.md`](../README.md#ownership--parallel-work) and
[`Subsystems/Face Subsystem.md`](../../Subsystems/Face%20Subsystem.md). Short
version: **Youssef owns `models/face/`**; do not mix face edits with physiology
or shared-doc edits in the same PR unless the change is a one-line status bump.

## Design boundary with fusion

- `StateMachine` → `StateReport` is **within-subsystem** channel fusion.
- Continuous fields on `StateReport` (PERCLOS, closure_ms, gaze_off_road_s,
  validity, eye_channel_available, …) are the contract DMS fusion will consume.
- `dms_face.alerts.Alerter` and `StateReport.should_alert` are for `run.py`
  demos only. Cabin buzzers in the integrated system belong to the alert
  subsystem.

## Command reference

```bash
python run.py
python run.py --calibrate --profile youssef
python run.py --video clip.mp4 --log results.csv
python run.py --no-display --duration 60
python run.py --ir
python bench.py --source image --resolutions --json bench_pi5.json
python calibrate_camera.py
```

Keys while running: `q` quit · `c` recalibrate · `m` full mesh ·
`i` show EAR landmark indices · `r` reset counters · `s` snapshot · `space` pause.

## Layout

```
models/face/
├─ src/dms_face/     package (landmarker, metrics, blink, perclos, state, …)
├─ models/           face_landmarker.task + canonical_face_model.obj
├─ profiles/         per-driver calibration (gitignored JSON)
├─ tests/            deterministic unit suite
├─ docs/             ARCHITECTURE / VALIDATION / EVIDENCE
├─ run.py            live / video entrypoint
├─ bench.py          throughput measurement
├─ calibrate_camera.py
└─ install_pi.sh
```
