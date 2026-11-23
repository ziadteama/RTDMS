# Live demo dashboard

One full-screen page for the audience. It shows:

- the camera with the face mesh, and the current fusion alert;
- tiles for eyes/drowsiness, phone use, drinking and the Garmin watch heart rate;
- frame rate, processing time per frame, Pi → watch alert round trip, CPU temperature, CPU load and power.

It only **reads** what the Pi already serves. It changes nothing on the Pi and stores nothing.

| Source | Port | Used for |
|---|---|---|
| Camera server (`rtdms-pi --stream-port 8080`, or `rtdms-camera`) | 8080 | `/status` (eyes, phone, drinking, fps, ms, temp) and `/stream.mjpg` (the browser loads it directly) |
| Pi runtime (`rtdms-pi --port 8090`) | 8090 | `/alert` (fusion decision), `/physio` (watch), `/health` (every 5 s) |

A source that does not answer shows **offline**. It never shows a guess.

## Run it

On the Pi (standard library only, any Python 3.11+):

```bash
python3 ~/rtdms-demo/dashboard/server.py          # then open http://<pi>:8000 on the laptop
```

On the laptop, reading the Pi over the network:

```bash
python server.py --pi-host <pi-ip>                # open http://localhost:8000
```

Rehearse without the Pi. This shows scripted data with a **SIMULATED DATA** badge, so it is never live:

```bash
python server.py --mock
```

Copy it to the Pi from the repo root:

```bash
scp -r demo/dashboard <user>@<pi>:~/rtdms-demo/
```

## On the day

1. Start the product unit on the Pi (`rtdms-pi-user`: camera, Bluetooth, runtime). Then start `server.py`.
2. Open `http://<pi>:8000` on the projector laptop and press **F** for full screen.
3. Check that all four dots in the top right are green: Camera, Fusion, Watch, Pi health.
4. Prefer the LAN or the Pi hotspot over Tailscale, because a relayed connection makes the video lag.

## What the numbers mean

- **Processing / frame** is the sum of the model stage times the camera reports (`/status` `ms`). No end-to-end measurement from capture to alert exists yet, so the page does not claim one.
- **Pi → watch alert** is the Bluetooth round trip from an alert change to the watch's echo, median and p95 (`/health` `physio_diag`). It appears once the watch has received alerts.
- **Drinking** is debounced here with the classifier's own numbers (`hybrid_alerts.py`: 1.5 s window, p ≥ 0.7, 70 % of samples). It is shown as a detection only: fusion does not alert on drinking (decision D28).

Tests: `pytest demo/dashboard/tests`.
