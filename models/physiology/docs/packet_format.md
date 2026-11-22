# Garmin RR packet format (watch → Pi)

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

## Version 1

### Layout (little-endian)

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

## Version 2

Opt in with `RrPacket(..., version=2)`. `encode` defaults to v1 through the packet default;
v1 decoding remains supported. All multibyte values are little-endian.

| Offset | Size | Field | Meaning |
|---:|---:|---|---|
| 0 | 1 | `version` | `2` |
| 1 | 1 | `flags` | bit 0 HR_VALID, bit 1 SPLIT, bit 2 ACK, bit 3 ECHO_VALID, bit 4 CONTACT; bits 5–7 reserved |
| 2 | 2 | `seq` | uint16 packet counter |
| 4 | 4 | `watch_ms` | uint32 watch uptime milliseconds |
| 8 | 1 | `hr` | uint8 bpm, 0 when HR_VALID is clear |
| 9 | 1 | `motion` | uint8 wrist motion energy of the ~1 s batch, computed on the watch |
| 10 | 1 | `echo_seq` | uint8 echo sequence, meaningful only with ECHO_VALID |
| 11 | 1 | `rr_count` | 0–4 |
| 12 | 2 × n | `rr_ms[n]` | uint16 RR intervals, oldest first |

Length must equal `12 + 2 * rr_count` (12–20 bytes). Invalid lengths/counts raise
`RrCodecError`. ACK acknowledges the wearer response; CONTACT means worn. SPLIT means the
batch continues. v1 yields `contact=None`, `motion=None`, `ack=False`, `echo_seq=None`.
For encoding, HR/contact/ACK/echo value fields determine their flags; SPLIT comes from flags.
Absent v2 motion encodes as zero; absent contact encodes as false. Set both explicitly when
simulating a worn watch. Unknown reserved flag bits are ignored on decode.

## Clocks: which time to trust

`rx_monotonic` and `rx_wall` record arrival. Accepted frames pass through `WatchClock.add(frame)`
to produce `t`, a Pi monotonic sample time from the unwrapped watch timer. Its offset is the
minimum `rx_monotonic * 1000 - watch_ms` over the last 300 seconds of Pi arrival time. Sliding
min/max deques give amortised O(1) updates. Sample time never exceeds arrival time.
`offset_spread_ms` is observed max−min delay variation; `late_packets` counts placements more
than 2 seconds before arrival. Both reset on NEW_SESSION. Duplicate/late frames must be dropped.

A reconnect burst retains its original times while a low-delay observation remains in the
window. A cold start or outage longer than the window cannot reveal unknown buffering delay;
the spread does not include unknown minimum one-way latency. Wraps are unwrapped assuming less
than half a uint32 timer cycle between accepted frames. Small offset corrections can move
sample time backwards; no monotonic clamp hides that correction.

Feed primary HR with `hr_stream.add(frame, t)`. Secondary HRV needs no API change:

```python
from dataclasses import replace

t = watch_clock.add(frame)
hr_stream.add(frame, t)
hrv.add(replace(frame, rx_monotonic=t))
```

The standalone receiver remains unchanged. HRV callers choose whether to supply placed time.
`HrStream` retains one latest batch per Pi-second bin for ten minutes; split packets cannot
inflate coverage. Startup and missing seconds count against the 80% valid-HR coverage over
30 seconds. Bad quality takes precedence for age >5 s, contact false, motion ≥160 (provisional
until bench testing), or a >25 bpm jump within 1 s. v1 contact/motion remain unknown.
Baseline uses good batches in the first 300 session seconds, available after 120 good occupied
seconds; it persists after ring eviction. Trend is least-squares bpm per 600 s over the last
600 s, also requiring 120 good occupied seconds. Gaps never count toward that duration.
Quality is captured at ingestion; snapshots do not retrospectively upgrade historical data.
Latest valid HR remains available when stale, with `quality=bad`; an empty stream has no age.
NEW_SESSION clears all HR history. Earlier-bin clock corrections are ignored by HrStream;
corrections within the current bin replace that sample. These signals are quality/context,
not a fatigue detector.

## Duplicates, loss, gaps and restarts (receiver rules)

`d = (seq - last_seq) mod 65536`

| Case | Rule |
|---|---|
| `d == 0` | duplicate: dropped, counted |
| `1 ≤ d < 32768` | new packet; `d - 1` packets were lost (counted, feeds the quality flag) |
| `d ≥ 32768` | older than the last one (late or re-sent): dropped, counted |
| `seq == 0` and `last_seq != 65535` (app restarted streaming), or `watch_ms` went backwards by > 5 s (watch rebooted) | new session: sequence tracking resets, nothing counted as lost |
| `watch_ms` jumped > 3 s from the last packet | a gap in the beat stream: marked so the HRV window does not join beats across it |
