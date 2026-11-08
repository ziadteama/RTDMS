# Pi deployment: camera stream (face mesh + drowsiness + phone)

The scripts the RTDMS Raspberry Pi 5 runs, copied as deployed (2026-11). One process owns the IR
camera and serves a live page on `http://<pi>:8080` with:

- the face mesh drawn on the image (`--mesh`, MediaPipe Face Landmarker through `dms_face` + LiteRT);
- drowsiness: eye closure, blinks, PERCLOS from `models/face` (`scripts/drowsiness.py`);
- phone alerts from the v2 model: call and texting (`scripts/hybrid.py`, models in
  `models/action_v2/`, see [../models/README.md](../models/README.md)).

| Script | What it does |
|---|---|
| `start_stream.sh` | **Current setup**: face mesh + drowsiness + v2 phone alerts, no box detector (`--hybrid --no-detect`), image rotated 180° (the camera is mounted upside down) |
| `start_stream_v1.sh` | Old setup: det_v2d phone / drink boxes (every 2nd frame) + drowsiness |
| `install.sh` | Offline install of the runtime into `.venv` from a `wheels/` folder (no internet on the Pi) |
| `power_log.sh` | Logs 5 V input, throttling flags and temperature every 2 s to `power.log` |
| `power_check.sh` | One-off power check (PMIC 5 V reading, throttling, USB current limit, dmesg) |

## Layout on the Pi

The scripts expect this folder (`~/rtdms` on the Pi), not the repo layout:

```
~/rtdms/
  start_stream.sh, start_stream_v1.sh, install.sh, power_log.sh   <- this folder
  distraction/      <- copy of models/distraction (src, scripts, configs, models)
  face/src/         <- copy of models/face/src  (dms_face)
  face/models/      <- copy of models/face/models (face_landmarker.task)
  wheels/           <- aarch64 Python 3.13 wheels for the packages in install.sh (not in git)
  .venv/            <- made by install.sh
```

`configs/pipeline.yaml` points at `../face/models/face_landmarker.task`, which resolves the same way
in the repo (`models/face/models/`) and on the Pi (`~/rtdms/face/models/`).

## Run

```bash
bash install.sh                      # once
nohup ./start_stream.sh > stream.log 2>&1 &
curl -s localhost:8080/status        # check it is up
```

From a PC on the Pi's wired link, forward the page with SSH (`-L 8080:localhost:8080`) and open
`http://localhost:8080`. To go back to the old setup, stop the stream
(`pkill -f scripts/stream.py`) and start `start_stream_v1.sh` instead.
