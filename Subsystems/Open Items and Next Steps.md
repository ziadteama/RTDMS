---
title: "Open Items and Next Steps"
tags:
  - backlog
  - status
status: current
updated: 2026-11-23
---

# Open Items and Next Steps

↑ [[Home]] | [[Project Log 2026-11]] | [[MVP Readiness]] | [[Orchestration Playbook]]

The single list of what is **not** done. Update it when something moves.

## Hardware work (needs the Pi, the phone or a car)

| Item | State | Notes |
|---|---|---|
| BLE pairing mode (replace open mode) | not started | The Pi currently runs in DEV open mode (no token; PR pi/ble-open-mode). Build: Pi accepts the first phone for 2 minutes after a button press or `rtdms-pair --open`, the app's "Find my Sahi unit" connects and stores a server-issued token. Acceptance criteria in [[Phone-Pi Link]] (Pairing). Open mode must not ship |
| Run the Pi runtime (`pi/`) on the real Pi | **BLE part running** (22 Nov) | `rtdms-pi-user` (BLE only, `--no-camera`, port 8090, dev open mode) runs on the Pi and advertises `RTDMS-Pi`. 207 Docker tests pass. Camera, buzzer and incident parts are not run on the Pi |
| **Bench spike**: one GATT service with the Garmin characteristic + ten phone ones, phone and watch together; Wi-Fi hotspot on `wlan0` alongside | not run | Go criteria in [[Phone-Pi Link]]. The Pi hardware agent was stopped before it started |
| Pi hotspot (`wlan0`, 5 GHz) and the in-app Wi-Fi join | not tested | Only the Tailscale route has been used so far |
| Garmin watch on the Pi alongside the phone service | not tested | Watch is available (23 Nov, on the dev machine USB in Garmin mode) |
| Crash detector on real motion (bumps, drops, braking) | replay tests only | Stillness thresholds untested |
| ColorOS background kill and the "monitoring paused" status | not tested | |
| Concurrent CPU / fps / temperature budget with all models, Bluetooth and hotspot | not measured | `.cursor/rules/pi-performance-pipeline.mdc` |
| The Pi rebooted by itself twice on 22 Nov (uptime under a minute at 22:50 and 23:05) | unexplained | No reboot history (`last` empty) and no previous-boot journal. Check power supply and the 5 V rail before any long test |
| Camera server autostart | **done (linger on, 22 Nov)**; camera ribbon detached on purpose for now | `rtdms-camera` systemd user service (PR #46) runs `~/rtdms/start_stream.sh`, restarts on crash, starts at boot. Stopped while the camera is detached. Known issue: `stream.py` exits 0 when the camera is missing, so systemd restarts it every 3 s instead of failing |
| Phone eye calibration on the real phone | **flow verified on the phone (22 Nov); sync to the Pi not yet** (needs the Pi camera server, or the BLE `calibrate` command, which the app prefers when the link is Bluetooth) | Dev build `ba793815` (PR #55): camera preview, face found at about 10 Hz, user finished the calibration. Still to check: Save → Pi `/status` shows `calibrated (phone)` (the Pi camera server is stopped while the ribbon is detached), voice/haptics, onboarding order |
| Settings dropdown fix (PR #48) on the real phone | **needs the phone** | Squeezed vertical labels came from the Compose Picker; replaced with value + sheet. Only checked by tests |

## Heart rate (Garmin) — plan in [[Physiology New Approach]]

| Item | State |
|---|---|
| P0: fusion ignores physiology for live alerts; no default heart-data log | **done on branches, not merged** (`fusion/physio-guard`, `physio/no-default-log`) |
| Contract v1.3 CR (one `t`, physio v2 fields, 60 s clock, packet v2) | not posted |
| P1: watch capability check (accelerometer, contact, vibration, notify subscribe, battery) | needs the user: watch USB mode → MTP, or the Windows build machine |
| P2–P5: HR pipeline, sync, phone HR UI, shadow score | not started |
| P6–P7: wrist vibration + "I'm OK", unresponsive-driver SOS | later |
| Remove the WESAD artifact and "Heart rate shows fatigue" string from the live path | in P2 / P4 |

## App

| Item | State |
|---|---|
| Bluetooth transport (A3) behind `PiTransport` | **built, merged and checked on the phone (22 Nov, user)**: connects with no code, reconnects, falls back and returns. Bluetooth off now shows "Bluetooth is off" (#72) instead of the raw "device powered off" error. Not yet checked: BLE calibration sync to the Pi, screen off beyond 2 min on a long drive, reconnect after a Pi restart (user reported reconnect fine) |
| Wi-Fi joined only during video sessions, then released (A4) | not started |
| UI polish and redrawn screens with an `impeccable` critique (A5) | not started; the Stitch project still shows the old design |
| Keep-awake guard on the Drive screen | fixed (PR #55, `suppressDeactivateWarnings`) |
| Settings has no way back to pairing once a unit is saved | **done (#70, 22 Nov)** | Row "Connect a different unit" in Settings; status row shows Bluetooth or Wi-Fi |
| Demo mode should switch off when real contacts are added | reported |
| Clip handling: resumable download, consent before sharing | not started |

## SOS and relay

| Item | State |
|---|---|
| Per-request logging in the relay (numbers masked) | not done |
| WhatsApp session logged out (401) | **fixed 22 Nov 17:05** | Re-linked with `relay/deploy/relink-whatsapp.sh`; health says `connected` and it survives restart and `kill -9`. Cause of the logout unknown; watch for it again (session expiry is a known risk) |
| Real app → relay → WhatsApp test with demo mode off | pending (user); the relay is connected again |
| Cause of the blocked link in SMS (carrier or recipient) | unconfirmed; ask the recipient to check Spam and blocked |
| Relay boot start | **done 22 Nov**: linger is on for the dev machine user, so `rtdms-relay` starts at boot. Not yet tested by an actual reboot |
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

- ~~Flaky first jest run on cold trees~~ **fixed (#70):** `testTimeout` 60 s; 700 tests pass with a cleared cache.
- ~~`stream.py` exits 0 when it finds no camera~~ **fixed (#68, deployed 22 Nov 17:12):** it exits 1; the unit uses `Restart=on-failure`, 30 s backoff, stops after 5 failures in 10 min. Checked on the Pi with the camera detached. Re-enable the service when the ribbon is back: `systemctl --user reset-failed rtdms-camera && systemctl --user enable --now rtdms-camera`.
- `ruff` reports 5 errors in `models/distraction` (`hybrid.py`, `hybrid_alerts.py`, `stream.py`) that were already on main; clean them up.
- BLE numbers that missed budget: command round trip p95 96–135 ms (< 100 ms), reconnect including a scan 2.8–6.6 s (< 5 s). Re-measure with the phone; the app connects directly to the remembered device.
- Not measured: Garmin watch with the phone service, 5 GHz hotspot next to BLE, fps with camera plus BLE, Android background behaviour.

- Fusion thresholds (`eye_closure_s`, `offroad_gaze_s`, `phone_s`, sensitivity) are stored by the Pi runtime but not applied; the face and fusion owners must read them.
- Camera frames do not yet reach the Pi's incident buffer, so a saved clip has no video yet.
- The incident HTTP server uses temporary port 8081 until merged into :8080.
