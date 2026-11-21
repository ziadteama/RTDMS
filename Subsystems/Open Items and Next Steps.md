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
| Run the Pi runtime (`pi/`) on the real Pi | not run | Merged and passes 154 Docker tests. Needs deploying; the Pi currently runs only the camera server |
| **Bench spike**: one GATT service with the Garmin characteristic + ten phone ones, phone and watch together; Wi-Fi hotspot on `wlan0` alongside | not run | Go criteria in [[Phone-Pi Link]]. The Pi hardware agent was stopped before it started |
| Pi hotspot (`wlan0`, 5 GHz) and the in-app Wi-Fi join | not tested | Only the Tailscale route has been used so far |
| Garmin watch on the Pi alongside the phone service | not tested | Watch availability unknown |
| Crash detector on real motion (bumps, drops, braking) | replay tests only | Stillness thresholds untested |
| ColorOS background kill and the "monitoring paused" status | not tested | |
| Concurrent CPU / fps / temperature budget with all models, Bluetooth and hotspot | not measured | `.cursor/rules/pi-performance-pipeline.mdc` |
| The Pi rebooted by itself twice on 22 Nov (uptime under a minute at 22:50 and 23:05) | unexplained | No reboot history (`last` empty) and no previous-boot journal. Check power supply and the 5 V rail before any long test |
| Camera server autostart | unclear | An instance came up at boot with different arguments; we restarted `~/rtdms/start_stream.sh` by hand at 23:05. Make it a systemd unit (`pi/deploy/systemd/rtdms-pi.service` exists, not installed) |

## App

| Item | State |
|---|---|
| Bluetooth transport (A3) behind `PiTransport` | not started |
| Wi-Fi joined only during video sessions, then released (A4) | not started |
| UI polish and redrawn screens with an `impeccable` critique (A5) | not started; the Stitch project still shows the old design |
| Keep-awake guard on the Drive screen | reported, not fixed |
| Demo mode should switch off when real contacts are added | reported |
| Clip handling: resumable download, consent before sharing | not started |

## SOS and relay

| Item | State |
|---|---|
| Per-request logging in the relay (numbers masked) | not done |
| Real app → relay → WhatsApp test with demo mode off | pending (user) |
| Cause of the blocked link in SMS (carrier or recipient) | unconfirmed; ask the recipient to check Spam and blocked |
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

- Fusion thresholds (`eye_closure_s`, `offroad_gaze_s`, `phone_s`, sensitivity) are stored by the Pi runtime but not applied; the face and fusion owners must read them.
- Camera frames do not yet reach the Pi's incident buffer, so a saved clip has no video yet.
- The incident HTTP server uses temporary port 8081 until merged into :8080.
- Codex quota returns at 23:01 on 22 Nov.
