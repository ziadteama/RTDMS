# Physiology Subsystem — Evidence

Results from the hardware-in-the-loop campaign, with the ESP32 wearable mocked in software.
Campaign notes and reasoning: `Subsystems/HIL Test Campaign.md` in the vault.

> [!IMPORTANT]
> **Environment caveat.** Except where a row explicitly says *Pi*, every result below was produced
> in the Docker Python 3.11 reference container on **x86_64**, not on the Raspberry Pi 5. The Pi
> went offline partway through the campaign. Correctness results transfer; **timing, CPU and memory
> results do not** and must be re-run on the target before they count as evidence.
>
> **A second caveat on CPU specifically.** The rig transports packets over TCP. Production uses BLE,
> where every notification arrives as a D-Bus `PropertiesChanged` signal marshalled through
> `dbus-fast` into the same event loop. TCP `recv` does not pay that cost. **Every CPU figure here
> is a lower bound on production.**

## Status summary

| Gate | Result | Environment |
|---|---|---|
| Unit / lint / type suite | **80 passed**, ruff clean, mypy clean (13 files) | Docker 3.11 |
| Suite on target hardware | 54 passed (at the point the Pi was last reachable) | **Pi, 3.13.5, aarch64** |
| BIDMC clinical HR accuracy | **0.5049918437361341 bpm MAE**, p95 1.6482 bpm | **Pi** + Docker, bit-identical |
| HR accuracy vs generator truth | ≤ **0.05 bpm** across a 26× MTU sweep | Docker |
| Memory stability (30 min) | RSS slope **+0.00 MB**, all buffers bounded | Docker |
| Steady-state CPU | **0.19%** of one core | **Pi** |
| Peak RSS | **~108 MB** (target 120, hard max 150) | **Pi** |
| Queue bounded under 33× overload | high-water **== cap**, drops counted, 0 decode errors | Docker |
| Fatigue suppression under fault | **0 leaks** across 8 fault types | Docker |
| MCU reset recovery | **0 outputs lost** (was 120 of 240) | Docker |

## Accuracy

### Clinical reference (BIDMC record 01)

| Metric | Value |
|---|---|
| Samples | 60,001 (480 s) |
| Evaluated outputs | 504 |
| **HR MAE** | **0.5049918437361341 bpm** |
| p95 absolute error | 1.6481895837457063 bpm |

Reproduced **bit-identically** on Python 3.11/x86_64 and Python 3.13/aarch64, and again after every
change in the campaign. It is the regression canary: any movement in that digit string means
processing behaviour changed.

### Against generator ground truth

The waveform generator emits true beat indices, so HR is scored against truth rather than itself.

| Scenario | Truth beats | Mean HR | Expected | Error |
|---|---:|---:|---:|---:|
| Clean 60 bpm | 180 | 60.01 | 60.0 | 0.01 |
| Clean 75 bpm | 225 | 75.00 | 75.0 | 0.00 |
| batch=3 (ATT MTU 23) | 180 | 60.00 | 60.0 | 0.00 |
| batch=7 | 180 | 60.00 | 60.0 | 0.00 |
| batch=20 | 180 | 60.01 | 60.0 | 0.01 |
| batch=79 (MTU 247) | 180 | 60.05 | 60.0 | 0.05 |
| Drift + noise (σ=300) | 180 | 60.01 | 60.0 | 0.01 |
| Ramp 50→120 bpm | 255 | 85.18 | 85 (ramp mean) | — |

**The MTU risk is closed for correctness.** Across a 26× change in packet size the error stays
≤0.05 bpm against a ≤3 bpm gate, so peaks straddling packet boundaries are neither double-counted
nor missed. The *cost* side (batch=3 means ~6× more peak-detector invocations) still needs the Pi.

## Robustness

### Fault injection — fatigue suppression holds

| Scenario | Reasons raised | Fatigue leak |
|---|---|---|
| Motion burst | CLIPPING, ARTIFACTS, INSUFFICIENT_BEATS | **0** |
| Clipping | CLIPPING, ARTIFACTS, FLATLINE | **0** |
| Flatline | ARTIFACTS, FLATLINE | **0** |
| Contact loss | SENSOR_FAULT, CLIPPING, FLATLINE | **0** |
| Saturation | CLIPPING, ARTIFACTS | **0** |
| FIFO overflow | SENSOR_FAULT, ARTIFACTS | **0** |
| Packet loss 5% | PACKET_LOSS, ARTIFACTS | **0** |
| Sequence wraparound | ARTIFACTS | **0** |

No fatigue probability ever escaped while quality was BAD — the invariant the "models report, fusion
decides" boundary depends on. Sequence wraparound (65535 → 0) raised **no** false packet-loss event.

### Overload — degrades honestly

`mock_wearable --firehose` against a consumer throttled to 4 ms/frame, ~33× overload:

```
packets_received 4000   dropped_frames 3879   decode_errors 0
queue_high_water 64     (cap 64)
downstream: 55 gap events, 11,565 samples accounted lost
```

Drops reconcile with what the tracker independently counted as lost (3,879 × 3 ≈ 11,637 vs 11,565,
the difference being packets in flight). Under overload the system **reports degradation rather than
emitting plausible-but-wrong heart rates**.

### Long run — no leak

30 minutes of 100 Hz data (1.8M samples): RSS slope **+0.00 MB** in steady state, interval deque
bounded at 62, raw ring buffer exactly at its 12,000-sample cap, output cadence 1.24/s.

## Defects found and their status

| ID | Defect | Found by | Status |
|---|---|---|---|
| **P0-A** | MCU reset silenced output for as long as the service had run (120 of 240 outputs lost) | Code reading, then measured | **FIXED** — 0 lost |
| **P0-B** | MCU reset pinned `packet_loss_fraction` at ~1.0 permanently; quality could never return to GOOD | Code reading | **FIXED** — verified on Pi |
| **P0-C** | Any packet gap discards the entire interval history | **Measurement only** | **OPEN** — see below |
| P1 | A sensor that never connects sat in `WARMUP` forever instead of escalating to `STALE` | codex review | **FIXED** + regression test |
| P1 | Wrong-rate frames refreshed the freshness timestamp before being dropped, masking staleness | codex review | **FIXED** + regression test |
| P1 | One malformed packet killed the whole service (no decode guard) | Code reading | **FIXED** |
| P1 | Unbounded acquisition queue | Code reading | **FIXED** — bounded, counted |
| P1 | `LogisticModel.probability` raised on non-finite input, killing the service loop | WP-11 agent | **FIXED** — suppresses + flags |
| P2 | Double publish per feature boundary, double-weighting every 5th HR sample | Code reading | **FIXED** — schema v2 |
| P2 | `BoundedOutputSink` installed only by the CLI wrapper | codex review | **OPEN** — ledger 5.6-5.8 PARTIAL |

### P0-C — still open

Packet loss sweep on merged `main`:

| Loss | HR yield |
|---|---:|
| none | **70%** |
| 2.5% | 39% |
| **5%** | **10%** |
| 10% | 9% |
| 33% | 8% |

`_reset_signal_state()` clears the entire interval deque on **any** `sample_gap`. A one-packet gap
discards the accumulated history, so HR availability collapses 7× at a loss rate BLE routinely
exceeds. `ARCHITECTURE.md:116` requires resetting only the *affected* state. Tracked as WP-15.

## Not closed by this campaign

Only the "physiology alone" row of `VALIDATION.md:116-122` is addressed. Still open:

- **All Pi timing/CPU/memory numbers** — the Pi went offline; must be re-run on target.
- **Concurrent-CV contention** — impossible today: no camera and no AI HAT+ are attached.
- **Real BLE transport** — no ESP32 and no second BLE adapter. `BleakSampleSource` is exercised
  through a fake client, and the wire format through TCP, but never over a radio.
- **PRV vs ECG agreement**, PPG-DaLiA, BUT PPG.
- **Fatigue-model LOSO validation** — no trained artifact exists; only an untrained
  `dummy-untrained-DO-NOT-DEPLOY` fixture that returns a constant 0.5 to exercise the code path.
  **No fatigue number in this document carries predictive meaning.**
- **MAX30102 sensor-domain transfer** and the wrist-motion 80%-usable-windows risk.
