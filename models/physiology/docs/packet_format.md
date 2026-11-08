# Garmin RR packet format (watch → Pi), version 1

The shared contract between the Connect IQ watch app (`garmin/rr_stream`, Monkey C) and the Pi
receiver (`src/dms_physiology/garmin_rr.py`). Both sides must change together; bump `version` on
any change. This is separate from the ESP32 PPG packet in `protocol.py`.

## Transport

| Item | Value |
|---|---|
| Roles | Watch = BLE central (GATT client). Pi = BLE peripheral (GATT server, advertising). |
| Service UUID | 16-bit `0xFFF0` (`0000fff0-0000-1000-8000-00805f9b34fb`), advertised with Flags `0x06` (LE only, General Discoverable). Garmin watches only report scan results for devices that advertise a 16-bit service UUID in General Discoverable mode; a device advertising only a 128-bit service UUID is never seen. `0xFFF0` is a common vendor-test value, so the characteristic below keeps a unique 128-bit UUID and the watch accepts a device only if that characteristic is there. |
| Characteristic UUID | `1375193a-7edb-4a34-b3f2-18130239c8a8`, properties: write, write-without-response |
| Direction | Watch writes one packet per write. The Pi never sends anything back. |
| Rate | One packet per sensor-listener batch, about 1 per second. |
| Size limit | ≤ 20 bytes per write (Connect IQ `Characteristic.requestWrite` rejects longer values). |

## Layout (little-endian)

| Offset | Size | Field | Meaning |
|---:|---:|---|---|
| 0 | 1 | `version` | `1` |
| 1 | 1 | `flags` | bit 0 `HR_VALID`: heart rate below is a real reading; bit 1 `SPLIT`: this batch had more than 5 RR intervals and continues in the next packet; bits 2-7 reserved, 0 |
| 2 | 2 | `seq` | Packet counter, uint16, +1 per packet, wraps 65535 → 0, starts at 0 when the app starts streaming |
| 4 | 4 | `watch_ms` | `System.getTimer()` on the watch when the batch arrived, uint32 ms (watch uptime clock) |
| 8 | 1 | `hr` | Heart rate in bpm (0 when `HR_VALID` is clear) |
| 9 | 1 | `rr_count` | Number of RR intervals that follow, 0-5 |
| 10 | 2 × n | `rr_ms[n]` | RR (beat-to-beat) intervals, uint16 ms each, oldest first |

Total = 10 + 2 × `rr_count` bytes, so 10 to 20 bytes. A packet whose length does not match its
`rr_count`, or with an unknown `version`, is rejected and counted as a decode error.

### Example (from the unit tests)

`01 01 07 00 E8 03 00 00 49 02 31 03 2A 03`

| Bytes | Field | Value |
|---|---|---|
| `01` | version | 1 |
| `01` | flags | `HR_VALID` |
| `07 00` | seq | 7 |
| `E8 03 00 00` | watch_ms | 1000 |
| `49` | hr | 73 bpm |
| `02` | rr_count | 2 |
| `31 03` | rr_ms[0] | 817 ms |
| `2A 03` | rr_ms[1] | 810 ms |

## Clocks: which time to trust

The watch clock and the Pi clock are not synchronised.

- **Pi receive time is the timestamp.** Every packet is stamped on arrival with
  `time.monotonic()` (for intervals, alignment with camera frames, which use the same clock) and
  `time.time()` (wall clock, for logs). These are what fusion uses.
- **`watch_ms` and `seq` are for ordering and gap-finding only.** They are never mixed with Pi time.

## Duplicates, loss, gaps and restarts (receiver rules)

`d = (seq - last_seq) mod 65536`

| Case | Rule |
|---|---|
| `d == 0` | duplicate: dropped, counted |
| `1 ≤ d < 32768` | new packet; `d - 1` packets were lost (counted, feeds the quality flag) |
| `d ≥ 32768` | older than the last one (late or re-sent): dropped, counted |
| `seq == 0` and `last_seq != 65535` (app restarted streaming), or `watch_ms` went backwards by > 5 s (watch rebooted) | new session: sequence tracking resets, nothing counted as lost |
| `watch_ms` jumped > 3 s from the last packet | a gap in the beat stream: marked so the HRV window does not join beats across it |
