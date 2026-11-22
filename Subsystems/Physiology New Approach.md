---
title: "Physiology New Approach — heart rate from the Garmin, three devices in sync (Nov 2026)"
tags:
  - subsystem
  - physiology
  - fusion
  - garmin
  - plan
aliases:
  - physio pivot
  - HR pipeline plan
status: in-progress
updated: 2026-11-23
code_path: models/physiology
---

# Physiology New Approach

↑ [[Home]] | [[Physiology Subsystem]] | why: [[Physiology Decision Log]] | replaces the role in
[[Physiology Fusion Approach]] | process: [[Orchestration Playbook]]

Decided with the user on 2026-11-23. **The Garmin FR265 stops being a fatigue detector.** It
gives a clean heart-rate stream, tells the system when that stream can be trusted, vibrates on
the wrist, and confirms an unresponsive driver. Watch, Pi and phone share one time model.

## Why

The evidence in [[Physiology Decision Log]] settles it:

- WESAD scored 0.545 (chance).
- On MPD-DF, HR scored 0.76, but drive time alone scored 0.84, and HR added +0.006 on top of it.
- The typical driver's first drowsy window comes around minute 91 of the drive, so heart signals
  mostly track time spent driving.

At the same time the code had sync and privacy problems. Payload `t` used three different clocks.
Watch packets were stamped on arrival, so a minute of buffered HR landed as "now" after a
reconnect. The phone wrote its clock only on connect. Fusion beeped on a chance-level WESAD score.
The receiver saved heart data by default.

## What heart rate does in fusion (D24)

| Role | Live? | Rule |
|---|---|---|
| **Vital-sign check** | Yes, emergency path only | No pulse while worn, or HR < 40 / > 150 at good quality, shortens the unresponsive-driver countdown. Missing HR never blocks it |
| **Quality gate** | Yes | `hr_quality != good` turns all physiology input off. Quality is never evidence |
| **Fatigue score** | **Shadow only** (weight 0) | 2-input logistic (HR vs the driver's first 5 min, HR trend) trained on MPD-DF, within-person AUROC ≈ 0.76. Logged next to every decision. Its weight rises only if a paired camera + watch test shows a benefit |
| **Drive-time break reminder** | Yes | A gentle reminder after 2 h, labelled as time on task, not physiology |

Fusion never beeps on physiology alone. The live "physio confirms → MAX" rule is removed (P0,
branch `fusion/physio-guard`).

## What we take from the Garmin (packet v2, ≤ 20 B)

| Field | Use |
|---|---|
| `hr` (1 Hz optical) | **Primary signal** |
| `contact` | Not worn → HR `bad` |
| `motion` (1 s wrist motion energy, computed on the watch) | Quality only, plus "wrist still" for the SOS path |
| `watch_ms` | Sync: places each sample on the Pi clock |
| RR intervals (0–4) | Secondary: PRV for Diagnostics when coverage ≥ 0.8; never a fusion input |
| `ACK` flag | "I'm OK" from a button press or wrist shake (vibration phase) |

## One pipeline on the Pi

```mermaid
flowchart LR
  W[Watch packet v2] --> D[garmin_rr decode v1/v2]
  D --> S[SequenceTracker]
  S --> C[WatchClock<br/>watch_ms to Pi time]
  C --> H[HrStream<br/>quality, baseline, delta, trend]
  H --> R[PhysioReport]
  R --> F[fusion: vital signs, gate, shadow score]
  R --> P[phone physio notify]
  R --> X[/health]
```

`HrStream` is pure and synchronous: a 10-min ring, O(1) work per packet, no asyncio. The WESAD
artifact and the hand-stepped coroutine leave the runtime path (`pi/src/rtdms_pi/sources.py`).

## Time: two clocks, two jobs (D25)

- **Phone = what time it is.** It has correct network time. Every timestamp that leaves the Pi is
  UTC epoch ms in phone time. Time zones are only for display on the phone.
- **Pi monotonic = how long, and which came first** (fusion, frames, HR, incidents). It never
  jumps and keeps working when the phone is away. The phone stamping on arrival is late by tens to
  hundreds of milliseconds.
- **Watch → Pi:** `offset = min(rx_mono − watch_ms)` over 5 min, and each sample is timed at
  `watch_ms + offset`. A buffered burst after a reconnect lands at its true times.
- **Phone → Pi:** the `clock` write repeats every 60 s; the Pi keeps the lowest-delay offset of the
  last 10.
- After a boot, the Pi sets its system clock from the phone if it is off by more than 2 s (logs and
  clip names only; logic never uses it).

## Privacy (D26)

- The Pi saves no heart data. The standalone receiver writes CSV only with `--csv` /
  `RESEARCH_LOG=1`, for consented research sessions (P0, branch `physio/no-default-log`).
- The phone keeps trip HR (one sample per 30 s) on the phone only, with a Settings switch "Save
  heart rate with trips" and delete-with-trip. This is a documented, consented exception to
  [[4.3 Ethics]].
- Location is used only inside the SOS, which the driver can cancel, as for a crash.

## Hardware change (D27)

The Garmin replaces the MAX30102 bracelet and the vibration motor in the BOM. The driver must wear
a Garmin with our Connect IQ app open.

## Phases

| Phase | What | Branches | State |
|---|---|---|---|
| P0 | Fusion ignores physiology for live alerts; no default heart-data log | `fusion/physio-guard`, `physio/no-default-log` | **done, not merged** (fusion 8 tests, Pi 207, physiology 132 pass) |
| P1 | Half-day watch check: accelerometer with HR/RR, contact, vibration, subscribing to a Pi notify, battery over 30 min | `physio/watch-api-check` | needs the user + watch |
| P2 | Packet v2, `WatchClock`, `HrStream`, slim `GarminPhysioSource` | `physio/hr-pipeline`, `pi/hr-source` | not started |
| P3 | One `t` (`pi/.../clock.py`), 60 s clock writes, phone uses payload `t`; contract v1.3 CR | `pi/one-clock`, `app/one-clock` | not started |
| P4 | Phone HR + quality dot, trip-HR switch | `app/hr-v2` | not started |
| P5 | MPD-DF shadow score + break reminder | `physio/mpddf-score`, `fusion/physio-shadow` | not started |
| P6 | Watch vibration + ACK; Pi↔watch latency (target < 100 ms) | `physio/watch-alert`, `pi/watch-alert` | later |
| P7 | Unresponsive-driver SOS (`EmergencyMonitor` in fusion → `alert.emergency` → `triggerSos('unresponsive')`) | `fusion/emergency`, `app/unresponsive-sos` | later |

## Pi budget

| Item | Budget |
|---|---|
| Whole physiology path | < 1 % of one core (hard gate 2 %); event-driven, about 1 packet/s |
| Extra RSS | < 5 MB |
| Camera fps | No change beyond noise with watch + phone connected |
| Garmin loss | < 2 % with the phone connected |
| Extra BLE | 1 clock write per 60 s; physio notify ≤ 1 Hz, sent on change |

## Orchestration

MAIN (interactive) owns P0, the contract CR, every device step, gates and merges, and docs.
Implementation goes to Codex from a `faithful-brief`, cross-reviewed by agy:

- PHYSIO lane: `models/physiology/`;
- PI lane: `pi/`;
- APP lane: `app/`.

At most two delegates at once, on disjoint directories. No code against an un-ACKed CR on
`~/RTDMS-coord/BOARD.md`.

## Verification

- **Unit:** packet v1/v2; WatchClock places a 60-packet reconnect burst within 50 ms of the true
  times; HrStream tables; every payload `t` comes from `clock.py`; physiology alone → no alert.
- **Bench:**
  1. **Sync, 1 h with all three devices:** watch offset spread p95 < 100 ms; phone offset spread
     p95 < 100 ms; Bluetooth off for 30 s puts the buffered HR at the right times; a hand clap on
     camera vs the wrist motion spike lines up within 200 ms.
  2. **Quality:** rest, steering, reaching, loose strap, watch off. Report how much of the time the
     signal is usable. This is availability only, with no chest strap.
  3. **Budget:** `pi/tools/verify_on_pi.sh`.

## Watch on the dev machine (23 Nov)

The FR265 on USB shows up as `091e:0003`, a vendor-specific interface bound to the kernel
`garmin_gps` driver. That is Garmin's own USB mode, not file transfer.

- To copy an app: on the watch, Settings → System → USB Mode → **MTP**, then an MTP client
  (`gvfs-backends` or `jmtpfs`).
- Building the app here needs Java 17, the Connect IQ SDK for Linux and the developer key. The
  build scripts (`garmin/build.ps1`, `sideload.ps1`) are Windows-only.
