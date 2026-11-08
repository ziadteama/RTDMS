# Garmin Forerunner 265: steps 1 and 2 (go / no-go)

Date: 2026-11-07. Watch: Forerunner 265 (worn on the wrist, at rest). PC: Windows 11, built-in
Bluetooth, bleak. Connect IQ SDK 9.3.0.

## Step 1: does the built-in "Broadcast Heart Rate" carry RR intervals?

`tools/check_garmin_broadcast.py`, 120 s (log: `step1_broadcast_fr265.txt`).

- Watch found as "Forerunner" (E0:48:24:D2:7A:54), standard Heart Rate Service 0x180D.
- 217 Heart Rate Measurement notifications in ~108 s (~2 per second), 0 malformed.
- Flags byte: `0x04` for the first seconds (contact detection supported, no skin contact yet), then
  `0x06` (skin contact). Bit 4 (RR present) was never set. Heart rate 8-bit, 62-75 bpm.
- Verdict: **RR present: no.** The broadcast gives heart rate only, so it cannot feed HRV
  features (RMSSD, SDNN, pNN50, CVNN, median IBI). Option A rejected; option B confirmed.

## Step 2: does a Connect IQ app get RR intervals from the wrist sensor?

`garmin/rr_check` (watch app; `Sensor.registerSensorDataListener` with `:heartBeatIntervals`,
period 1 s), built with `garmin/build.ps1`, copied over USB with `garmin/sideload.ps1`.

- The app shows heart rate, **RR/s = 1** per ~1 s batch and **last RR = 817 ms**.
- 60000 / 817 = 73 bpm, consistent with the resting heart rate and with ~1.2 beats per second
  (batches of 1, sometimes 2 intervals).
- Verdict: **RR intervals are available to a Connect IQ app on the FR265.** Option B is viable.

Still to measure (later steps): RR agreement with a reference (chest strap or manual pulse over
1 min), RR dropout during arm movement, and battery drain with the app open.

## Note: the Windows PC cannot stand in for the Pi as receiver

Tried 2026-11-07 so the watch could be tested without the Pi. The laptop's Bluetooth
(Realtek, USB VID_0BDA PID_5852) reports peripheral-role support and can publish a plain BLE
advertisement (status STARTED), but Windows' GATT server (`GattServiceProvider`) never advertises
the RR service: connectable + discoverable -> ABORTED at once, other settings stay at CREATED,
with the Bluetooth settings page open too. The watch app therefore stayed on "SCANNING".
`garmin_receiver` now checks the advertisement status on Windows and exits with an error instead
of silently waiting. The receiver runs on the Pi (BlueZ via bless), which is the real target.

## Watch -> Pi over Bluetooth: working (2026-11-08)

RR Stream (watch, BLE central) -> `garmin_receiver` on the Pi (BlueZ via bless, GATT peripheral).
Pi log of the first real session: seq 24-32 at ~1 per second, HR 73 bpm, RR 672-871 ms
(60000/73 = 822 ms), 0 lost, 0 decode errors; every row stamped with Pi receive time.

What it took (each one blocked the link on its own):

1. **The watch only reports devices that advertise a 16-bit service UUID in General Discoverable
   mode.** A Pi advertising only the 128-bit service was never seen (611 / 1,177 scan results,
   none from the Pi). Fix: the RR service UUID is 16-bit `0xFFF0`; the RR characteristic keeps a
   unique 128-bit UUID so a stranger's FFF0 device is rejected. (Garmin forum bug reports confirm
   the 16-bit / discoverable behaviour.)
2. **BlueZ adds the discoverable Flags only while the adapter is discoverable** -> `bluetoothctl
   discoverable on`, timeout 0 (in the receiver start script).
3. **LE-only controller** (`ControllerMode = le` in /etc/bluetooth/main.conf) -> Flags 0x06,
   and advertising interval 100-150 ms (`Min/MaxAdvertisementInterval = 160/240`) instead of the
   1.28 s kernel default. Original file kept as main.conf.rtdms-backup.
4. **bless 0.2.6 registered only the first of two services**: with a separate 16-bit "finder"
   service first, the RR service was missing from the GATT table (watch: connected, "svc no").
   Fix: a single service.
5. Profile registration in the watch app copies Garmin's sample (no `:descriptors` entry for a
   write-only characteristic), and the app keeps looking for the characteristic for 8 s after
   connecting before giving up.

## First HRV numbers from the watch (src/dms_physiology/garmin_hrv.py, tools/replay_rr.py)

5-minute session, resting, watch on the wrist part of the time (receiver log
garmin_rr_20261011_221839.csv, replayed with `python tools/replay_rr.py <log>`):

- 321 packets, 0 lost, 0 artifacts rejected after the watch was put on.
- **156 of 321 packets carried no RR at all**: the wrist sensor reports beats in bursts with
  silences of several seconds. Coverage (accepted beat time / 60 s window) was 0.3-0.9, so many
  windows are DEGRADED or BAD by design.
- Beats on either side of a silence are not neighbours, so successive differences are only
  taken when `elapsed between packets <= RR + 1 s batch + 0.15 s`; RMSSD / pNN50 need >= 10
  true pairs.
- Last window (VALID, coverage 0.88, 60 beats): HR 68.4 bpm, RMSSD 43.4 ms, SDNN 36.9 ms,
  pNN50 0.21 - normal resting values. No reference recording yet (chest strap) to check them.
