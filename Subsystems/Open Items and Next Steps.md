---
title: "Open Items and Next Steps"
tags:
  - backlog
  - status
status: current
updated: 2026-11-22
---

# Open Items and Next Steps

↑ [[Home]] | [[Project Log 2026-11]] | [[Orchestration Playbook]]

The single list of what is **not** done. Update it when something moves.

## Hardware work (needs the Pi, the phone or a car)

| Item | State | Notes |
|---|---|---|
| BLE pairing mode (replace open mode) | not started | The Pi currently runs in DEV open mode (no token; PR pi/ble-open-mode). Build: Pi accepts the first phone for 2 minutes after a button press or `rtdms-pair --open`, the app's "Find my Sahi unit" connects and stores a server-issued token. Acceptance criteria in [[Phone-Pi Link]] (Pairing). Open mode must not ship |
| Run the Pi runtime (`pi/`) on the real Pi | **BLE part running** (22 Nov) | `rtdms-pi-user` (BLE only, `--no-camera`, port 8090, dev open mode) runs on the Pi and advertises `RTDMS-Pi`. 207 Docker tests pass. Camera, buzzer and incident parts are not run on the Pi |
| **Bench spike**: one GATT service with the Garmin characteristic + ten phone ones, phone and watch together; Wi-Fi hotspot on `wlan0` alongside | not run | Go criteria in [[Phone-Pi Link]]. The Pi hardware agent was stopped before it started |
| Pi hotspot (`wlan0`, 5 GHz) and the in-app Wi-Fi join | not tested | Only the Tailscale route has been used so far |
| Garmin watch on the Pi alongside the phone service | not tested | Watch availability unknown |
| Crash detector on real motion (bumps, drops, braking) | replay tests only | Stillness thresholds untested |
| ColorOS background kill and the "monitoring paused" status | not tested | |
| Concurrent CPU / fps / temperature budget with all models, Bluetooth and hotspot | not measured | `.cursor/rules/pi-performance-pipeline.mdc` |
| The Pi rebooted by itself twice on 22 Nov (uptime under a minute at 22:50 and 23:05) | unexplained | No reboot history (`last` empty) and no previous-boot journal. Check power supply and the 5 V rail before any long test |
| Camera server autostart | **done (linger on, 22 Nov)**; camera ribbon detached on purpose for now | `rtdms-camera` systemd user service (PR #46) runs `~/rtdms/start_stream.sh`, restarts on crash, starts at boot. Stopped while the camera is detached. Known issue: `stream.py` exits 0 when the camera is missing, so systemd restarts it every 3 s instead of failing |
| Phone eye calibration on the real phone | **flow verified on the phone (22 Nov); sync to the Pi not yet** (needs the Pi camera server, or the BLE `calibrate` command, which the app prefers when the link is Bluetooth) | Dev build `ba793815` (PR #55): camera preview, face found at about 10 Hz, user finished the calibration. Still to check: Save → Pi `/status` shows `calibrated (phone)` (the Pi camera server is stopped while the ribbon is detached), voice/haptics, onboarding order |
| Settings dropdown fix (PR #48) on the real phone | **needs the phone** | Squeezed vertical labels came from the Compose Picker; replaced with value + sheet. Only checked by tests |

## App

| Item | State |
|---|---|
| Bluetooth transport (A3) behind `PiTransport` | **built and merged (#61/#63), partly checked on the phone**: connection and health read seen. Still to check: Diagnostics link row text, reconnect after a Pi restart, screen off 2 min on ColorOS, fallback to HTTP, BLE calibration sync |
| Wi-Fi joined only during video sessions, then released (A4) | not started |
| UI polish and redrawn screens with an `impeccable` critique (A5) | not started; the Stitch project still shows the old design |
| Keep-awake guard on the Drive screen | fixed (PR #55, `suppressDeactivateWarnings`) |
| Settings has no way back to pairing once a unit is saved | open | Pair screen is reachable only through `sahi://pair`; add a Settings row |
| Demo mode should switch off when real contacts are added | reported |
| Clip handling: resumable download, consent before sharing | not started |

## SOS and relay

| Item | State |
|---|---|
| Per-request logging in the relay (numbers masked) | not done |
| **WhatsApp session logged out (401)** | **needs the user** | The relay (now a service) reports `whatsapp_logged_out`. Re-link the dedicated number: Linked devices → Link a device, scan the QR the relay prints. Back up the auth dir first; do not delete it blindly |
| Real app → relay → WhatsApp test with demo mode off | pending (user), after the re-link |
| Cause of the blocked link in SMS (carrier or recipient) | unconfirmed; ask the recipient to check Spam and blocked |
| Relay boot start | **needs the user**: `sudo loginctl enable-linger teamacs` on the dev machine. The service itself restarts on crash |
| Host the relay on an always-on server instead of the dev machine | open |
| WhatsApp ban risk (unofficial library, linked spare number) | accepted by the user; session expiry needs re-linking |

## Product questions (need the team)

1. How does a driver get the **pairing QR** when the Pi has no screen? Proposal: print it on the unit label at manufacturing.
2. Who mounts the camera and sets the driving position: the driver or an installer?
3. One driver per car, or several profiles?
4. Report wording: 4.3.1.1 says nothing is transmitted over Wi-Fi or Bluetooth, but the design uses a local phone link and a cloud relay with a third party (Meta). The consent text and the report should say so honestly.
5. Fleet and OEM use needs a separate manager dashboard and consent model: out of scope here.
6. Validate the needs table with **at least 5 real drivers** (15-minute test on the wireframes).

## Housekeeping

- **Flaky first jest run** on cold trees (`controls.test.tsx` timeout at 16 s); passes on reruns. Find the cause or raise the timeout.
- `stream.py` exits 0 when it finds no camera, so systemd restarts it forever; make it fail (non-zero) and stop retrying.
- BLE numbers that missed budget: command round trip p95 96–135 ms (< 100 ms), reconnect including a scan 2.8–6.6 s (< 5 s). Re-measure with the phone; the app connects directly to the remembered device.
- Not measured: Garmin watch with the phone service, 5 GHz hotspot next to BLE, fps with camera plus BLE, Android background behaviour.

- Fusion thresholds (`eye_closure_s`, `offroad_gaze_s`, `phone_s`, sensitivity) are stored by the Pi runtime but not applied; the face and fusion owners must read them.
- Camera frames do not yet reach the Pi's incident buffer, so a saved clip has no video yet.
- The incident HTTP server uses temporary port 8081 until merged into :8080.
- Codex quota returns at 23:01 on 22 Nov.
