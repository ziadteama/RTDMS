# Physiology Subsystem — Evidence

Results from the hardware-in-the-loop campaign, with the ESP32 wearable mocked in software.
Campaign notes and reasoning: `Subsystems/HIL Test Campaign.md` in the vault.

> [!IMPORTANT]
> **Environment caveat.** The Pi went offline for the middle portion of this campaign (Chain A/B,
> WP-14/15, the optimisation work) and every result from that stretch was Docker x86_64 only. It
> reconnected on 2026-08-29 and the full gate — tests, lint, types, BIDMC, CPU/RSS MTU sweep,
> thermal — was re-run directly on target. Rows below are now marked **Pi** wherever they carry
> hardware evidence from that run; anything still marked **Docker** has not yet been re-verified on
> target (mainly the fault-injection matrix and the 30-min soak, which are expensive to repeat and
> whose logic doesn't depend on the architecture).
>
> **A second caveat on CPU specifically.** The rig transports packets over TCP. Production uses BLE,
> where every notification arrives as a D-Bus `PropertiesChanged` signal marshalled through
> `dbus-fast` into the same event loop. TCP `recv` does not pay that cost. **Every CPU figure here
> is a lower bound on production**, Pi-measured or not.

## Status summary

| Gate | Result | Environment |
|---|---|---|
| Unit / lint / type suite | **81 passed** (3 async resource warnings, no failures), ruff clean, mypy clean (13 files) | **Pi, 3.13.5, aarch64** |
| BIDMC clinical HR accuracy | **0.5082470420003504 bpm MAE**, p95 1.7068 bpm, 420 outputs | **Pi**, bit-identical to Docker |
| HR accuracy vs generator truth | ≤ **0.05 bpm** across a 26× MTU sweep | Docker |
| CPU at realistic MTU (batch=3, ATT MTU 23) | **1.31%** of one core | **Pi** |
| CPU at batch=20 / batch=79 | 0.22% / 0.08% of one core | **Pi** |
| Peak RSS, all MTUs | **108.5–109.7 MB** (target 120, hard max 150) | **Pi** |
| Thermal during full gate | 47.7°C → 51.6°C, `throttled=0x0` throughout | **Pi** |
| Memory stability (30 min) | RSS slope **+0.00 MB**, all buffers bounded | Docker |
| Queue bounded under 33× overload | high-water **== cap**, drops counted, 0 decode errors | Docker |
| Fatigue suppression under fault | **0 leaks** across 8 fault types | Docker |
| MCU reset recovery (P0-A) | **0 outputs lost** (was 120 of 240) | Docker + **Pi** (packet-loss sweep, below) |

## Accuracy

### Clinical reference (BIDMC record 01)

| Metric | Value |
|---|---|
| Samples | 60,001 (480 s) |
| Evaluated outputs | 420 |
| **HR MAE** | **0.5082470420003504 bpm** |
| p95 absolute error | 1.7068158994204723 bpm |

Reproduced **bit-identically** on Python 3.11/x86_64 (Docker) and Python 3.13/aarch64 (Pi). The
504→420 output-count drop from the original WP-13 baseline is expected, not a regression: WP-3
removed a double-publish-per-boundary bug, so each feature window now publishes once instead of
twice. The MAE digit string is the regression canary — any movement means processing behaviour
changed.

**A real regression was caught here.** After Chain A's merge (schema v2, uppercase `VALID`/
`DEGRADED` state strings), `validate_bidmc.py` was still filtering on the old lowercase `"good"`/
`"degraded"` vocabulary, so it silently raised on every run instead of scoring anything. This had
been merged to `main` without re-running the check. Fixed in `40a47e7`; the baseline above is
post-fix and is what both Docker and the Pi now reproduce.

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
nor missed.

**The cost side is now closed too, on real hardware:**

| Config | CPU %/core | Peak RSS |
|---|---:|---:|
| batch=3 (ATT MTU 23, realistic) | **1.31%** | 108.5 MB |
| batch=20 | 0.22% | 109.6 MB |
| batch=79 (MTU 247) | 0.08% | 109.7 MB |

All under the 2% CPU hard gate and 150 MB RSS hard gate at every MTU, including the realistic worst
case (batch=3 is above the 1% *target* but inside the hard gate). Measured on the Pi 5 at governor
`ondemand`, `throttled=0x0` before and after — 2026-08-29, via `tools/verify_on_pi.sh`.

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
| **P0-C** | Any packet gap discarded the entire interval history | **Measurement only** | **PARTIALLY FIXED** (WP-15) — see below |
| P1 | A sensor that never connects sat in `WARMUP` forever instead of escalating to `STALE` | codex review | **FIXED** + regression test |
| P1 | Wrong-rate frames refreshed the freshness timestamp before being dropped, masking staleness | codex review | **FIXED** + regression test |
| P1 | One malformed packet killed the whole service (no decode guard) | Code reading | **FIXED** |
| P1 | Unbounded acquisition queue | Code reading | **FIXED** — bounded, counted |
| P1 | `LogisticModel.probability` raised on non-finite input, killing the service loop | WP-11 agent | **FIXED** — suppresses + flags |
| P2 | Double publish per feature boundary, double-weighting every 5th HR sample | Code reading | **FIXED** — schema v2 |
| P2 | `BoundedOutputSink` installed only by the CLI wrapper | codex review | **OPEN** — ledger 5.6-5.8 PARTIAL |

### P0-C — partially fixed, not closed

`_reset_signal_state()` used to clear the entire interval deque on **any** `sample_gap`. WP-15
(`0ce26ca`) changed it to retain intervals that fall outside the discontinuity instead of wiping
everything. Re-measured on the Pi against current `main` (`packet_loss_indices`, batch=20, 120 s,
seed=5, reproducible via the snippet in `Subsystems/HIL Test Campaign.md`):

| Loss | Outputs | With HR | HR yield |
|---|---:|---:|---:|
| none | 120 | 60 | 50.0% |
| 2.5% | 120 | 60 | 50.0% |
| 5% | 120 | 60 | 50.0% |
| 10% | 120 | 38 | 31.7% |
| 20% | 120 | 37 | 30.8% |
| 33% | 127 | 42 | 33.1% |

This supersedes the original discovery-time table (`70%→10%` at 5% loss, a near-total collapse).
**The fix genuinely helps**: yield no longer collapses at 5% loss at all, and the degradation at
10%+ plateaus around 31–33% instead of continuing to fall. It does not fully close the defect —
yield at 10%+ loss is still roughly 20 points below baseline, and `ARCHITECTURE.md:116`'s
"only the affected window" requirement is only partially met. A further work package would be
needed to close this fully. WP-14 (dropping scipy from the runtime to save ~30 MB RSS) was
implemented, verified to reproduce BIDMC bit-identically, then **reverted** (`987b24b`): it pushed
CPU at the realistic batch=3 MTU from 1.97% to 3.27%, over the 2% hard gate, because the pure-numpy
IIR filter replacement is inherently sequential and can't be vectorised the way scipy's C
implementation is. scipy stays a runtime dependency.

## Not closed by this campaign

Only the "physiology alone" row of `VALIDATION.md:116-122` is addressed. Still open:

- **Concurrent-CV contention** — impossible today: no camera and no AI HAT+ are attached.
- **Real BLE transport** — no ESP32 and no second BLE adapter. `BleakSampleSource` is exercised
  through a fake client, and the wire format through TCP, but never over a radio. Every CPU number
  above is therefore still a lower bound on production, Pi-measured or not.
- **P0-C in full** — see above; a real but partial fix.
- **Ledger 5.6-5.8 PARTIAL** — `BoundedOutputSink` is installed only by the CLI wrapper; a raw sink
  passed directly to `PhysiologyService` can still raise into acquisition.
- **PRV vs ECG agreement**, PPG-DaLiA, BUT PPG.
- **Fatigue-model LOSO validation** — no trained artifact exists; only an untrained
  `dummy-untrained-DO-NOT-DEPLOY` fixture that returns a constant 0.5 to exercise the code path.
  **No fatigue number in this document carries predictive meaning.**
- **MAX30102 sensor-domain transfer** and the wrist-motion 80%-usable-windows risk.
- **The fault-injection matrix and the 30-min soak are still Docker-only** — logic-level results,
  not expected to differ on target, but not yet re-run there.
