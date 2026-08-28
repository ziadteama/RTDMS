---
title: "HIL Test Campaign — Physiology on the Pi"
tags:
  - subsystem
  - testing
  - validation
  - physiology
  - raspberry-pi
aliases:
  - HIL test
  - mock ESP32
status: in-progress
started: 2026-08-28
---

# HIL Test Campaign — Physiology on the Pi

↑ [[Home]] | [[Physiology Subsystem]] | [[Raspberry Pi 5 Target]] | [[Pi Setup Plan]]

Hardware-in-the-loop validation of the [[Physiology Subsystem]] on the real
[[Raspberry Pi 5 Target]], with the ESP32 wearable **mocked** — we act as the wearable and
stream the exact wire protocol at the Pi.

**Plan:** `C:\Users\ziadt\.claude\plans\i-wanna-plan-the-parallel-seahorse.md`
**Coverage ledger:** 130+ normative items extracted per the `faithful-brief` skill, before any
brief was written. Every delegated job carries its slice as explicit acceptance criteria and must
report per-item status.

---

## Why the ESP32 is mocked in software, not emulated over a radio

There is no ESP32, no second BLE adapter, and `btvirt` is not packaged on Trixie. Building a
virtual BLE stack from BlueZ source to test a decoder is disproportionate. Three layers instead:

| Layer | What it proves | Cost |
|---|---|---|
| **Socket rig** (`SocketSampleSource` + `mock_wearable.py`) | Codec, service, fault handling, latency, memory — the whole pipeline | Main effort |
| **`FakeBleakClient`** | The *real* `BleakSampleSource.frames()` production path, which has **never once executed** | Nearly free |
| **Bumble / `/dev/vhci`** | A genuine BlueZ→D-Bus→Bleak→notify loop, no radio | 1-day timebox, not critical path |

> [!warning] Honesty caveat that must reach the evidence file
> A TCP rig **understates production CPU**. BLE notifications arrive as D-Bus `PropertiesChanged`
> signals marshalled through `dbus-fast` into the same event loop; TCP `recv` does not pay that.
> **Every CPU number from the socket rig is a lower bound**, and must be labelled as such.

---

## Headline findings so far

### P0 — a single MCU reset bricks the subsystem, two independent ways

Both confirmed by reading the source. `docs/ARCHITECTURE.md:108` calls MCU reset a **normal
operating condition**.

> [!danger] P0-A — a reset silences the service for as long as it has been running
> `_reset_signal_state()` (`service.py:81-85`) does **not** reset `_last_hr_emit_index`. After a
> reset restarts `first_sample_index` at 0, the `end_index - _last_hr_emit_index >= hr_period`
> test in `_emit_if_due` goes deeply negative. **A reset at T+1h produces ~1 hour of total
> silence.** Fixed by WP-2.

> [!danger] P0-B — a reset permanently poisons packet loss
> `sample_step` is computed `% 2^32` (`protocol.py:136-138`), so a reset yields
> `sample_gap ≈ 4.29e9`, which `service.py:69` adds straight into `_lost_samples`.
> `packet_loss_fraction` pins at ~1.0 **forever**, `QualityReason.PACKET_LOSS` latches, and
> quality can never return to GOOD (`quality.py:53`). Fixed by WP-1 at the root.

**Consequence:** fixes land before measurements. Benchmarking first would record numbers the fixes
then invalidate.

### WP-0c — scipy costs 77 MB for three function calls

Measured on the Pi, 2026-08-28:

| Import set | RSS | Delta |
|---|---:|---:|
| Bare Python 3.13 | 8.9 MB | — |
| + numpy | 22.6 MB | +13.7 |
| **+ scipy.signal** | **99.6 MB** | **+77.0** |
| + bleak (full production set) | 103.1 MB | +3.5 |

The budget is **120 MB target / 150 MB hard max** ([[Physiology Subsystem#Resource budget Pi 5]]).
We are at **103 MB before doing any work at all** — roughly 17 MB of headroom to target.

scipy is used in **exactly three places**, all in `signal.py`:

| Call | Line | Replaceability |
|---|---|---|
| `butter(2, [0.5, 5.0], btype="bandpass", fs=100, output="sos")` | 63 | **Trivial** — the filter is fixed; precompute the SOS coefficients once |
| `sosfilt(sos, values, zi=zi)` | 72 | **Easy** — ~20 lines of numpy, a biquad cascade with state |
| `find_peaks(energy, height, distance, prominence)` | 113 | **Non-trivial** — prominence is fiddly, and this is the heart of the whole subsystem |

> [!important] Decision: measure first, do not remove scipy yet
> Removing scipy would reclaim 77 MB and take the floor to ~26 MB — turning a marginal gate into a
> comfortable one. But `find_peaks` replacement carries real accuracy risk, and peak detection is
> what the 0.50 bpm BIDMC result rests on.
>
> **Sequencing:** run the HIL test with scipy, record the real total RSS. It will likely land
> ~110–125 MB — *passing the 150 MB hard gate, probably missing the 120 MB target*. If it misses,
> WP-14 is costed and ready: reimplement all three in numpy with an equivalence test against scipy
> proving identical output on the BIDMC record. That equivalence test is what de-risks it.

---

## Work packages

| WP | What | Route | Status |
|---|---|---|---|
| 0a | Relax Python pin to `>=3.11`, add `verify-py313` | me | pending |
| 0b | Pi venv + runtime deps | me | **done** — scipy 1.18.1 + bleak wheels exist for cp313/aarch64 |
| 0c | Import-cost baseline | me | **done** — see above |
| 1 | `PacketTracker` signed step + sessions (fixes P0-B) | agy (worktree) | running |
| 2 | Loss accounting + post-reset rebasing (fixes P0-A) | chain A | pending |
| 3 | Single publish + injectable clock | chain A | pending |
| 4 | State machine `WARMUP/VALID/DEGRADED/STALE` + time-driven loop | chain A | pending |
| 5 | Robustness guards + `SessionHealth` | chain A | pending |
| 6 | Waveform + fault generator | agy (worktree) | running |
| 7 | Shared `_FramePump` + `SocketSampleSource` | chain B | pending |
| 8 | `tools/mock_wearable.py` | chain B | pending |
| 9 | `FakeBleakClient` tests | Sonnet | running |
| 10 | `--source` CLI + fusion probe + systemd unit | chain B | pending |
| 11 | `make_dummy_model.py` | Sonnet | running |
| 12 | `benchmark_pi.py` rewrite | pending | pending |
| 13 | Execute matrix + `docs/EVIDENCE.md` | pending | pending |
| **14** | **Drop scipy (conditional)** | conditional on WP-12 RSS | costed, not started |

### Delegation topology

- **Isolation:** agy write jobs run in dedicated `git worktree`s (`Z:\rtdms-wt\wp1`, `wp6`) so they
  cannot collide with the Sonnet agents working in the main tree. Each uses a distinct Docker
  compose project name (`-p physiology-wp1`) to avoid container collisions.
- **`/codex` is read-only** in this setup — it reviews, it cannot implement. It is therefore the
  independent-verification route, not an implementation route.
- **Chain A (WP-2→3→4→5) is strictly sequential on one agent** — all four touch `service.run`, and
  parallelising them guarantees conflict in a 150-line file.

---

## Test matrix

**A · Offline deterministic (virtual time)** — 20 scenarios. Headline: **A10 — MCU reset at t=90 s**
must produce the next output within 1 s, `packet_loss_fraction < 0.01`, a new `session_id`, and
VALID after warmup. That single test pins both P0 defects.

**B · HIL on the Pi (real sockets, real time)** — 8 scenarios. Headline: **B2 — the MTU sweep.**

**C · Bleak-specific (radio-free)** — 4 `FakeBleakClient` scenarios + the Bumble spike.

> [!warning] The MTU problem nobody had accounted for
> At the default ATT MTU of 23, a notification payload is 20 bytes → with a 10-byte header and
> 3 bytes/sample that is **3 samples per packet, ~33 packets/sec** — not the 5/sec the existing
> simulator assumes. `AdaptivePeakDetector.process` runs `find_peaks` **once per packet**, so real
> packet cadence drives CPU by roughly **6×**, inside a <1%-of-one-core budget. Every run sweeps
> `batch_size ∈ {3, 20, 79}` and records the assumed MTU.

---

## Pi state for this campaign

Boot config snapshotted to `~/dms/snapshots/` before any change (only one Pi — a bad config change
would brick the demo box). Venv at `~/dms/venv` with numpy 2.2.4, scipy 1.18.1, bleak.

Every run must set `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1` (`ARCHITECTURE.md:15`) and record governor, MTU, library versions, and that
the boot device is microSD. **Pick one governor and do not change it mid-matrix** — the
`ondemand`→`performance` switch proposed in [[Pi Setup Plan]] changes every number.

---

## What this campaign does NOT close

Only the **"physiology alone"** and **"thermal soak"** rows of `VALIDATION.md:116-122`. Still open:
concurrent-CV contention (no camera, no AI HAT+ — see [[Raspberry Pi 5 Target#Hardware gaps]]),
PPG-DaLiA / BUT PPG, PRV-vs-ECG agreement, fatigue-model LOSO, MAX30102 sensor-domain transfer, and
the wrist-motion 80%-usable-windows risk.

> [!tip] Highest evidence-per-EGP purchase available
> A ~500 EGP MAX30102 breakout wired to the Pi's I2C (which [[Pi Setup Plan]] already proposes
> enabling) would give **real optical data through the real signal path** — the only thing that
> touches the sensor-domain-shift risk. Different gate from this campaign, but cheap and high value.
