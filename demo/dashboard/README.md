# Live demo dashboard

One full-screen page for the audience. It shows:

- the camera (face mesh, no debug side column on the stream);
- a phone bezel with the live Sahi app screen (USB `adb` mirror) or a simulated app face in `--mock`;
- a status strip: fusion decision, eyes/drowsiness, phone use, drinking, Garmin heart rate.

It only **reads** what the Pi already serves. It changes nothing on the Pi and stores nothing.

| Source | Port | Used for |
|---|---|---|
| Camera server (`rtdms-pi --stream-port 8080`, or `rtdms-camera`) | 8080 | `/status` (eyes, phone, drinking, fps, ms, temp) and `/stream.mjpg` (relayed through :8000) |
| Pi runtime (`rtdms-pi --port 8090`) | 8090 | `/alert` (fusion decision), `/physio` (watch), `/health` (every 5 s) |
| USB phone (optional, laptop) | adb | `/phone.png` screencap of the Sahi app inside the bezel |

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

Laptop with the phone USB-connected and Sahi open (mirrors the app into the bezel):

```bash
adb reverse tcp:8081 tcp:8081   # if Metro is serving the app
python server.py --pi-host <pi-ip> --phone-mirror
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

1. Start the product unit on the Pi (`rtdms-pi-user`: camera, Bluetooth, runtime). Then start `server.py` (on the laptop with `--phone-mirror` if you want the app bezel live).
2. Open `http://localhost:8000` (or `http://<pi>:8000`) on the projector laptop and press **F** for full screen.
3. Check that the dots in the top right are green: Camera, Fusion, Watch, App, Pi.
4. Prefer the LAN or the Pi hotspot over Tailscale, because a relayed connection makes the video lag.

## What the numbers mean

- **Drinking** is shown as a detection only: fusion does not alert on drinking (decision D28). With `--held` on the camera, the held mouth+cup result is the light; older cameras fall back to the classifier drinking score averaged over 1.5 s.
- **Phone bezel**: with `--phone-mirror`, the page polls `/phone.png` from `adb exec-out screencap -p`. Without it, mock mode draws a Sahi-like face that follows the fusion alert; live mode without mirror shows “USB phone mirror off”.

Tests: `pytest demo/dashboard/tests`.
