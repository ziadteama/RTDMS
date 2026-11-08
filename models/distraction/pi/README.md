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

The Pi runs straight from a git clone of the repo, `~/rtdms-repo` (the Pi has no internet: bring
new commits as a git bundle from a PC, see Update below). The Python environment stays outside the
clone:

```
~/rtdms-repo/                 <- git clone; scripts run from models/distraction/pi/
~/rtdms/.venv/                <- made by install.sh (override with RTDMS_PYTHON=/path/to/python)
~/rtdms/wheels/               <- aarch64 Python 3.13 wheels for install.sh (not in git)
~/dms/venv/, ~/dms/garmin/    <- Garmin receiver venv, logs (models/physiology/tools/pi/)
```

The start scripts also still work from the older copy layout (`~/rtdms/start_stream.sh` next to
`distraction/`, `face/src/`, `face/models/`).

Pi-only settings (LiteRT face mesh, INT8 detector, no fisheye correction, slower pose) live in
`configs/profiles/pi.yaml`; both start scripts pass `--profile pi`, so the Pi runs the repo's
`configs/pipeline.yaml` unchanged. `configs/pipeline.yaml` points at `../face/models/face_landmarker.task`, which resolves the same way
in the repo (`models/face/models/`) and on the Pi (`~/rtdms/face/models/`).

## Run

```bash
cd ~/rtdms-repo/models/distraction/pi
nohup ./start_stream.sh > ~/rtdms/stream.log 2>&1 &              # camera page on :8080
bash ~/rtdms-repo/models/physiology/tools/pi/start_garmin_receiver.sh   # watch page on :8081
curl -s localhost:8080/status
```

From a PC on the Pi's wired link, forward the pages with SSH (`-L 8080:localhost:8080
-L 8081:localhost:8081`) and open `http://localhost:8080`. To go back to the old setup, stop the
stream (`pkill -f scripts/stream.py`) and start `start_stream_v1.sh` instead.

## Update

On the PC: `git bundle create rtdms.bundle main`, copy it to the Pi's home folder, then on the Pi:

```bash
cd ~/rtdms-repo && git pull ~/rtdms.bundle main
```

and restart both scripts. With internet on the Pi, a plain `git pull` (origin is GitHub) works too.
