---
title: "Pi Runtime — the rtdms-pi process"
tags:
  - subsystem
  - pi
  - runtime
  - ble
  - incidents
aliases:
  - Pi Runtime
  - rtdms-pi
status: ble-running-on-pi-camera-and-gpio-unverified
updated: 2026-11-22
---

# Pi Runtime — the `rtdms-pi` process

↑ [[Home]] | Link design: [[Phone-Pi Link]] | Contract: `contracts/pi-link/CONTRACT.md` | Device: [[Raspberry Pi 5 Target]] | Setup: [[Pi Setup Plan]] | Models: [[Face Subsystem]], [[Distraction Subsystem]], [[Physiology Subsystem]]
Related: [[Eye Calibration]]

One Python process (package `pi/`, entry point `rtdms-pi`) that joins the model outputs, runs `dms_fusion.decide()` on every frame, drives the buzzer, serves the phone over BLE, records incidents and answers health. **Status: code complete and Docker-verified on x86 (Python 3.11 and 3.13). Nothing here has run on the Pi yet.** Every claim about hardware is "not verified on hardware" until the Hardware queue (below) is cleared.

> [!warning] Docker is not the target
> All results below are from Docker on x86. Numbers and behaviour on the Pi 5 (BlueZ 5.82, Python 3.13, real camera) are not measured. See [[Agent Guide]] §4.

## Architecture

```
camera -> stream.pipeline_loop (models/distraction, imported, not forked)
            |  Shared.status setter hook (one call per frame)
            v
  StreamPipelineSource -> FrameResult(face, phone, fps, temp, camera_ok)
GarminPhysioSource <- BLE write 1375193a-...a8 (watch)          \
            v                                                    v
        Runtime.on_frame / 1 Hz watchdog -> dms_fusion.decide() -> PatternPlayer -> buzzer/vibration
            |                                         |
        RuntimeState (immutable snapshots)       alert/status/physio/health payloads
            |                                         |
   incidents (ring, store, clip)             PhoneService (BLE, one GATT service)  + debug HTTP
```

| Part | File(s) in `pi/src/rtdms_pi/` | Pattern |
|---|---|---|
| Frame and physio inputs | `sources.py` | `FrameSource` / `PhysioSource` protocols (strategy); scripted fakes for tests |
| Decision per frame | `runtime.py`, `state.py` | pure `decide()`, inputs older than 2 s (camera) / 10 s (watch) become `None` |
| Buzzer, vibration | `buzzer.py` | `PatternPlayer` worker thread, backends gpio / console / recording |
| Payloads | `payloads.py` | pure builders, validated against `contracts/pi-link/schemas`, notify <= 240 B |
| BLE | `ble/` | `GattPort` strategy (`BlessGatt`, `FakeGatt`), one UUID module, one validation point |
| Incidents | `incidents/` | ring buffer, store, MJPEG-AVI muxer, ffmpeg transcoder, HTTP routes |
| Pairing | `pairing.py`, `tools/factory_label.py` | pure QR-string builder; the same function serves the factory label and the CLI |
| Hotspot | `deploy/hotspot/` | `nmcli` AP scripts |
| Service | `deploy/systemd/rtdms-pi.service` | `Nice=-5`, `MemoryMax=3G` |

Invariants kept: models report and `fusion/` decides (the runtime only gates input freshness); bad or missing input becomes `None` / "unavailable"; no biometric data on disk (the Garmin receiver is built with `log=None`, `data.jsonl` uses an allowlist of status and alert keys).

## BLE service

Exactly as the contract: one service `0xFFF0` holding the Garmin write characteristic plus the ten phone characteristics (`alert`, `status`, `physio`, `settings`, `command`, `result`, `incident`, `clock`, `auth`, `health`). Garmin writes are handled first and synchronously.

**Notify schedule (contract v1.2, send on change).** The notifier sleeps on an `asyncio` event: a decision change (from a model thread, through `call_soon_threadsafe`) wakes it and the alert goes out at once. One coalesced 1 s tick covers the rest: alert keep-alive 1 Hz, status and physio only when their quantised payload changed plus a 5 s keep-alive each (the keep-alive gives a late subscriber a state). Outgoing notifies are built from the typed payload builders, encoded compactly and compared with the last sent bytes; they are not schema-validated unless `--debug-validate` (or `RTDMS_DEBUG_VALIDATE=1`). Command results and everything the phone writes stay validated. If the Garmin loss fraction over the last 60 packets exceeds 5 %, status and physio checks drop to half rate (recovers under 2 %).

**Auth and disconnects.** bless 0.2.6 has no disconnect callback, so `bless_gatt.py` watches BlueZ on D-Bus (`PropertiesChanged` of `org.bluez.Device1`, `Connected` false) and resets auth; the 300 s TTL stays as a fallback. The Device1 path is not passed by bless, so any peer disconnect (a Garmin watch too) resets auth. A write before auth raises `org.bluez.Error.NotAuthorized`.

Hardware facts and numbers: [[Phone-Pi Link]] and `pi/tools/link_spike/results/README.md`. Still unverified: one service with the watch and the phone connected, GPIO, the camera hook.

## User-service deployment (2026-11-22)

The runtime runs on the Pi as the systemd **user** service `rtdms-pi-user` (`pi/deploy/systemd/rtdms-pi-user.service`, installer `install-user-service.sh`, linger already on): `rtdms-pi --no-camera --ble --buzzer none --port 8090` (8080 belongs to `stream.py`), state in `~/.local/state/rtdms`, `Restart=on-failure`, `Nice=10`, `CPUWeight=20`, `IOSchedulingClass=idle` so it yields to the models. The system unit `rtdms-pi.service` carries the same priorities.

- Code and venv: `~/rtdms-pi/` (`pi/`, `fusion/`, `models/physiology/`, `contracts/`; venv with `--system-site-packages`, `pip install -e './pi[ble]'`: use the path, `pi` alone resolves to an unrelated PyPI package). Update with a tar-over-ssh of `pi/src`, then `systemctl --user restart rtdms-pi-user`.
- **DEV open mode:** `rtdms-pi --ble-open` / `RTDMS_BLE_OPEN=1` (default off) skips the BLE token, logs a WARNING at startup; `install-user-service.sh --open` writes the drop-in `rtdms-pi-user.service.d/open.conf`, running the installer without `--open` removes it. Insecure, dev only; replaced by a pairing mode ([[Phone-Pi Link]], Pairing).
- Pairing token: stays in `~/.local/state/rtdms/token` on the Pi (mode 0600); `rtdms-pair --force` prints the QR string (it contains the token and the Wi-Fi PSK: never commit it).
- `rtdms-camera` stays stopped while the camera is detached. The camera is not part of this unit; `--camera` comes with the camera bring-up.
- Wireplumber BLE-MIDI is disabled for the desktop image (see [[Phone-Pi Link]]).
- Uninstall: `install-user-service.sh --uninstall`.

## Heart rate, time and safety (contract v1.3, 23 Nov)

Plan and reasons: [[Physiology New Approach]].

- **Time:** `clock.py` `PhoneClock` keeps the smallest offset (`pi_mono_ms − phone_ms`) of the
  last 10 `clock` writes; every payload `t` is UTC epoch seconds in phone time with `t_src`
  ("pi" = Pi wall clock before any write). Incidents use the same offset on Pi monotonic time.
  Optional one-shot system-clock sync: `sync_system_clock` (default off).
- **Heart rate:** `garmin_source.py` decodes the watch packet (v1/v2) → `SequenceTracker` →
  `WatchClock` → `HrStream` (+ `RrHrv` for Diagnostics PRV). The heart-rate maths is cached at
  1 s / 5 s (the runtime asks per camera frame); ACK, echo, motion and ages are always fresh. No
  WESAD model, no `fatigue_probability`, nothing written to disk.
- **Safety:** `safety.py` owns the fusion `EmergencyMonitor` (eyes closed ≥ 8 s → MAX "driver not
  responding"; no response for 10 s with the watch / 20 s without / 5 s if HR is clearly abnormal
  → `alert.emergency = "unresponsive"`, which starts the phone's SOS countdown), the 2 h
  `BreakReminder`, and the MPD-DF shadow score (counted in `health.physio_diag`, never acted on).
- **Watch alert:** characteristic 0b `watch_alert` = 2 raw bytes `[pattern, seq]` on every
  change + 5 s keep-alive; the watch echoes the seq, giving round-trip p50/p95 in `physio_diag`.

## Boot and persistence (23 Nov, #92)

Goal: whenever the Pi has power, everything for the product or a presentation is up, with no manual step.

- **Unit:** `rtdms-pi-user` is the product unit: `--camera --rotate $RTDMS_ROTATE --stream-port 8080 --ble --buzzer none --port 8090`, `Restart=always` with backoff and no start limit, `Nice=0`, `MemoryMax=3G` (a leak fence). The hand-made `camera.conf` drop-in is retired (backup in `~/.config/rtdms/backup`). Site settings (rotation, extra flags) live in `~/.config/rtdms/deploy.env`, never overwritten.
- **Order:** `wait-bluetooth.sh` runs before start (adapter powered, discoverable for the watch; never blocks the camera). `rtdms-ready.service` runs `check.sh --wait 240 --boot` and logs "RTDMS READY" when camera, BLE and HTTP are up.
- **Scripts** (`pi/deploy/`): `install.sh` (idempotent, `--dry-run`, `--uninstall`, `--open|--secure`), `deploy.sh` (backup `.bak-<stamp>`, sync, restart), `check.sh` (fps, BLE, HTTP, throttled; reads interfaces only). Never touches eth0, tailscale0 or Wi-Fi.
- **System bits:** linger on, persistent journal, BLE controller LE-only with 100–150 ms advertising (backup `main.conf.rtdms-backup`).
- **Wi-Fi:** the phone-hotspot profile autoconnects (system-wide, password stored, priority 100, unlimited retries). A hotspot on `wlan0` is still a separate, untested item.
- **Still dev:** BLE open mode stays on (no token) until pairing mode exists.
- **Evidence:** one controlled reboot: camera 30 fps, BLE up, throttled 0x0, Wi-Fi back by itself.


## Incidents

20 s of status and alert history at 10 fps is held in memory (JPEG frames feed in later from the stream `Shared`; wiring is a TODO). A phone `incident` write is mapped onto the ring with the clock offset from the last `clock` write; the same `client_id` returns the same incident id. The clip is written as `clip.avi` at once and transcoded by a `nice 19` ffmpeg job to `clip.mp4`; `clip_ready` flips when it exists. Retention is 20 incidents and a 500 MB free-disk floor. HTTP (list, files, Range, `POST /incident`, bearer token) currently runs on a temporary port 8081 until merged into the single :8080 server.

## Settings and health

`health` comes from a probe that reads `/sys`, `/proc` and `vcgencmd`; any failed read omits the field, nothing is guessed. Settings are persisted in `state_dir/settings.json`; detector switches gate the inputs before `decide()`. **Thresholds (`eye_closure_s`, `offroad_gaze_s`, `phone_s`, `sensitivity`) are stored but not applied** because fusion and the face model own fixed thresholds (see the Need on the coordination board).

## Verify

```sh
docker compose -f pi/compose.yaml run --build --rm verify          # py3.11
docker compose -f pi/compose.yaml run --build --rm verify-py313
pi/tools/verify_on_pi.sh                                            # on the Pi (written, not run)
```

Last run 2026-11-21: py3.11 and py3.13 both green (see the PR bodies for the counts).

## Hardware queue

| # | Check | Why |
|---|---|---|
| H1 | Run `pi/tools/link_spike/` matrix A to D | Go / no-go in [[Phone-Pi Link]] |
| H2 | `pi/tools/verify_on_pi.sh` on Python 3.13 | Docker is not the target |
| H3 | GPIO buzzer pin 18 and vibration pin | `gpiozero` path never ran |
| H4 | `StreamPipelineSource` with the IR camera, per-frame hook cost | Hook is untested against the real pipeline |
| H5 | One bless service with watch + phone connected, 11 characteristics | Contract open question 1 (laptop-only run done 2026-11-22; watch and phone not yet) |
| H6 | Hotspot on 5 GHz channel 36, country EG, phone joins, Garmin loss unchanged | Contract open question 3 |
| H7 | systemd unit at boot and after a crash | User unit installed and running 2026-11-22; boot and crash restart not yet exercised |
| H8 | ffmpeg `libx264` clip time at `nice 19` under full load | Budget |
| H9 | Full concurrent budget (fps, CPU, temperature, `get_throttled`) before and after, per `.cursor/rules/pi-performance-pipeline.mdc` | P6 budget, M4 soak |

## Results

2026-11-22, `throttled=0x0`, 49 C: BLE service CPU 0.15-0.17% of one core under a 4-process synthetic load, about +14 MB RSS, 1.1 wake-ups/s idle, alert change p95 113 ms, command round trip p95 96 to 135 ms (connection-interval bound, phone re-test needed). Full tables in [[Phone-Pi Link]]. Camera, GPIO and fps are not measured.
