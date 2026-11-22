# BLE bench results, 2026-11-22 (Pi 5 <-> dev laptop, no phone, no Garmin, no camera)

Setup: `rtdms-pi --no-camera --ble --buzzer none` as the systemd user service `rtdms-pi-user` on the Pi
(BlueZ 5.82, bless 0.2.6, Python 3.13). Central: laptop with USB adapter `hci0` (bleak), 15-30 cm away.
The Pi's wireplumber BLE-MIDI GATT server was disabled first (see the hardware finding below).
Raw files here: `bench-idle-2026-11-22.json` (bench_link), `proc-sample-2026-11-22.jsonl` (proc_sample, one line idle, one connected).

| Check | Budget / expectation | Measured | Result |
|---|---|---|---|
| Characteristics visible | 11 in service 0xFFF0 | 11 (10 phone + Garmin) with the contract properties | PASS |
| Write before auth | rejected | rejected (ATT 0x0e before the NotAuthorized fix; 0x08 afterwards, not re-measured on air) | PASS |
| Notify rates, nothing changing | alert 1 Hz, status keep-alive 5 s, physio once | alert 0.99 Hz (max gap 1.04 s, 54 B), status 6 in 30 s, physio 0 after subscribe | PASS |
| Command round trip (write + result notify) | p95 < 100 ms | n=100, 0 failures, p50 91 ms, p95 96 ms, max 136 ms | PASS, narrow (dominated by the connection interval the central picks) |
| Alert change reaches the central | p95 <= 300 ms | n=31 flips: p50 95 ms, p95 113 ms, max 116 ms (laptop/Pi clock offset 68 ms +- ~55 ms removed) | PASS |
| Reconnect, 5 cycles, scan + connect + discover + auth | < 5 s each | 4.1, 3.8, 5.0, 2.8, 6.6 s: 2 of 5 over | FAIL as defined |
| Reconnect to a known address (no scan), 8 cycles | < 5 s | connect+discover 1.1-1.5 s, auth 0.25-0.3 s, total 1.6-1.8 s; with scan 1.6-6.2 s (the scan is the variable part, one 4.75 s outlier) | PASS for the phone case (the app remembers the device id) |
| Auth reset after reconnect | write rejected again | confirmed in 3 of 3 cycles that completed the check | PASS |
| dmesg | no bluetooth / brcmfmac errors | only init lines; `throttled=0x0`, 49 C | PASS |

## Efficiency budgets (process `rtdms-pi`, 4 busy-loop processes as synthetic load, 60 s, `proc_sample.py`)

| Budget | Idle (no central) | Connected (auth, subscribed to alert/status/physio/result) | Result |
|---|---|---|---|
| BLE <= 2% of one core (avg) | 0.17% | 0.15% | PASS |
| RSS extra <= 25 MB | 119 MB total; the same runtime without the BLE server is 105 MB (RSS of an in-process build), so BLE adds about 14 MB | 119.2 MB (+0.05 MB over 60 s) | PASS |
| 0 idle wake-ups beyond the timers | 1.1 voluntary context switches/s (the 1 Hz tick) | 1.07/s | PASS |
| Threads | 5 | 5 | n/a |

The vision-pipeline fps drop (<= 3%) is not measured: the camera is detached.

## Not measured

- Garmin coexistence, 5 GHz hotspot + BLE, camera + BLE fps (no watch, no camera, hotspot not run).
- Android phone behaviour (MTU 247 request, screen-off notifies, auto-reconnect): phone test pending.
- Clock offset for the alert-latency number is +- ~55 ms (two ssh round trips); the margin to 300 ms is large.
- Write-before-auth ATT code 0x08 after the NotAuthorized change was not re-read on air; unit-tested only.
- `physiology` shows `error` in `/health` when no Garmin watch is attached.

## Hardware findings

1. bless 0.2.6 enums are `Flag`, not int: `0 | prop` crashed the service on start. Fixed, test mirrors real bless.
2. The Pi desktop's wireplumber exposes a BLE-MIDI GATT service with an encrypted characteristic. An unpaired
   central that touches it starts SMP pairing (numeric comparison, nobody answers), pairing fails and the link
   drops (symptoms: ATT 0x0e, "device disconnected" during service discovery). Disabled with
   `~/.config/wireplumber/wireplumber.conf.d/90-rtdms-no-ble-midi.conf` (`monitor.bluez-midi = disabled`).
3. bless reports no disconnects; a D-Bus PropertiesChanged watch on `org.bluez.Device1.Connected` now resets auth.
   Any peer disconnect (including a Garmin watch) resets it, so the phone must re-auth after a rejected write.
4. Write-before-auth was ATT 0x0e (Unlikely Error); now `org.bluez.Error.NotAuthorized` (BlueZ maps it to 0x08).
5. Advertised name `RTDMS-Pi` equals the QR `B` field; a test pins both defaults.
