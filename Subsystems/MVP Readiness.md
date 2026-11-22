---
title: "MVP Readiness"
tags:
  - status
  - mvp
status: current
updated: 2026-11-22
---

# MVP Readiness

↑ [[Home]] | [[Open Items and Next Steps]] | [[Project Log 2026-11]]

**Question (22 Nov 2026):** is what we have enough for an MVP?

**Answer: enough for a phone-side MVP demo, not yet for a full end-to-end MVP.** The software chain from phone to Pi to WhatsApp is built and mostly verified. What is missing is the real driving chain: camera on the Pi, alerts from real models, the buzzer, and tests in a car.

Define the MVP as: *a driver mounts the unit, the Pi detects drowsiness / distraction / phone use and alerts with a buzzer, the phone shows it, and a crash sends a WhatsApp SOS.*

## What works (checked on real hardware)

| Piece | Evidence |
|---|---|
| Sahi app on a real phone (realme GT 6T), dev build | Runs, tabs, onboarding, diagnostics |
| Phone eye calibration (camera, MediaPipe, closed ratio) | Flow finished on the phone, 22 Nov |
| Phone ↔ Pi over Bluetooth LE, no code (dev open mode) | Connected, Pi health read over BLE with HTTP off |
| Pi BLE service cost | 0.15% of one core, +14 MB RSS, alert p95 113 ms |
| WhatsApp SOS relay, always on | systemd user service, WhatsApp `connected`, survives `kill -9`; real messages sent earlier |
| Pi distraction pipeline (YOLO + face mesh, v2 hybrid) | Ran on the Pi earlier with the camera |
| Pi camera service fails fast and backs off | Deployed and checked with the camera detached |
| Gates | App 700 jest tests, Pi 207 Docker tests, contracts validator |

## What blocks a real MVP

| # | Gap | Why it matters | Effort |
|---|---|---|---|
| 1 | **Camera plus BLE plus fusion never run together on the Pi** | The product is the alert from the camera; the budgets (fps drop ≤ 3%, CPU, temperature) are only measured for BLE alone | Reattach the ribbon, run `rtdms-camera` and `rtdms-pi-user`, measure |
| 2 | **Buzzer / vibration never wired on the Pi** | No physical alert yet; only the phone shows alerts | Hardware wiring plus a GPIO test |
| 3 | **Phone does not yet show a real Pi alert from the real models** | Alerts so far came from the test alert path | One drive-style session: close eyes, look away, hold a phone |
| 4 | **BLE is in dev open mode** | Anyone in range could control the unit; must not ship | Build pairing mode (button or `rtdms-pair --open`, server-issued token) |
| 5 | **Test SOS to a real number not yet sent** | The one safety promise of the app | Needs the user's `+20…` number; relay is ready |
| 6 | **Crash detector only replay-tested** | False crash alarms or missed crashes | Bump / drop / brake tests with the phone in a car |
| 7 | **Android background (ColorOS) untested** | If the OS kills the app while driving, nothing alerts or sends SOS | 2-minute screen-off test, then a long drive |
| 8 | **Wearable (MAX30102 heart rate) not built** | The physiological confirmation is part of the system design; the vision path works without it | Optional for a first MVP; state this honestly in the demo |
| 9 | **Pi rebooted by itself twice** | Unexplained; may be power | Check the 5 V supply before long tests |

## Recommended MVP scope

**In:** phone app, Pi with camera and the three vision alerts (eyes closed, off-road gaze, phone use), BLE link, buzzer, WhatsApp SOS, calibration.
**Out for now:** wearable heart rate, hotspot / Wi-Fi-only-for-video, clip sharing, UI redesign, fleet dashboard.

## Order to get there

1. Reattach the ribbon; run camera plus BLE together; record fps, CPU and temperature (gap 1).
2. Wire the buzzer and test the three alert patterns (gap 2).
3. Do the real alert session with the phone watching (gap 3).
4. Send the real test SOS (gap 5) and the screen-off test (gap 7).
5. Build pairing mode and turn open mode off (gap 4).
6. Car test: crash detector and a short drive (gap 6).

## Honest framing for the team and supervisor

- The **architecture and the link are proven**: BLE control path, always-on SOS relay, efficient Pi service.
- The **detection accuracy targets (≥ 85–90%, < 500 ms end to end)** are not yet measured on the full chain; the models were measured on datasets and in earlier Pi runs, not together with the link.
- Report wording (4.3.1.1 says nothing is sent over Wi-Fi or Bluetooth) must be updated: the design uses a local phone link and a cloud WhatsApp relay. See product question 4 in [[Open Items and Next Steps]].
