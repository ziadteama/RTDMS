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

## Milestone — the subsystem now runs on the target hardware

2026-08-28. First time this code has ever executed on the Pi.

```
26 passed                              # full suite, Python 3.13.5, aarch64
mean_hr_bpm: 60.0  state: good  score: 1.0  packet_loss_fraction: 0.0
```

The Python pin relaxation (WP-0a) works: `pip install -e ".[dev,train]"` succeeds on 3.13, and
`numpy 2.2.4` / `scipy 1.18.1` / `bleak` all resolve to cp313 aarch64 wheels.

### Resource measurements on the Pi (2026-08-28)

Measured **in-process**, with frame construction outside the timed region so startup and setup
cannot contaminate the steady-state figure.

| Data | CPU | % of one core at realtime | Peak RSS | Outputs |
|---|---:|---:|---:|---:|
| 70 s | 0.125 s | **0.18%** | 104.4 MB | 84 |
| 300 s | 0.582 s | **0.19%** | 107.9 MB | 360 |

> [!success] CPU passes comfortably; memory passes but with little room
> **CPU 0.19%** against a <1% target and 2% hard gate — a wide margin.
> **RSS ~108 MB** against a 120 MB target and 150 MB hard max — passes, but only ~12 MB of headroom.
>
> The memory story is entirely scipy: the import floor alone is 103 MB, so the actual working set
> is only about **5 MB**. Dropping scipy (WP-14) would take RSS to roughly 31 MB. Not blocking —
> we pass the hard gate as built — but it is the one lever that turns a tight number into a
> comfortable one.

> [!warning] Correction
> An earlier reading of this measurement put CPU at ~1.7%, from timing the whole process including
> interpreter startup and the numpy/scipy import (~0.95 s of fixed cost). That figure was wrong;
> the in-process numbers above supersede it. Recorded here rather than quietly deleted, because the
> methodology error is the point: **any CPU number that includes startup is meaningless for a
> long-running service.**

> [!important] The MTU risk is now quantified, not theoretical
> These numbers are at batch size 20. At the MTU-realistic batch size of 3, `find_peaks` runs ~6×
> more often, which would put CPU near **1.1%** — over the target. **B2, the MTU sweep, is the test
> that decides whether the CPU budget actually holds.**

The 104.4 → 107.9 MB growth between runs tracks the `InMemorySink` accumulating 84 → 360 output
dicts — the known unbounded-sink defect, not a leak in the processing path.

Also confirmed from the run: `fatigue_probability: null` and `model_version: null` — the model path
really is dead code (what WP-11 exists to fix). And `rmssd_ms: 0.0, sdnn_ms: 0.0, cvnn: 0.0`,
because the current synthetic signal is perfectly periodic with **zero** heart-rate variability —
which is precisely why WP-6's realistic generator matters: today's simulator cannot exercise the
PRV path at all.

## Measurement readiness (checked on the Pi before the soak)

| Primitive | Ledger | State |
|---|---|---|
| `vcgencmd get_throttled` | 12.13 | ✅ present → `0x0` |
| `/sys/class/thermal/thermal_zone0/temp` | 12.12 | ✅ 45.2 °C |
| `/sys/.../cpu0/cpufreq/scaling_cur_freq` | 12.14 | ✅ — but see below |
| `/proc/self/stat` fields 14/15/20, `CLK_TCK`=100 | 12.2 | ✅ |
| `/proc/self/status` VmRSS/VmHWM/ctxt switches | 12.3 | ✅ |
| cgroup v2 + `systemd-run --user --scope -p MemoryMax=` | 12.11 | ✅ delegated, works |
| **`/proc/pressure/*` (PSI)** | 12.15 | ❌ **not enabled in this kernel** |

> [!warning] Ledger 12.15 — DEFERRED, not dropped
> PSI is not compiled/enabled in the running kernel. Enabling it needs `psi=1` in
> `/boot/firmware/cmdline.txt` **and a reboot**. This is the only Pi we have, PSI is a
> nice-to-have rather than a gate, and [[Pi Setup Plan]] mandates one config change at a time.
> **Decision: defer.** Memory pressure will be inferred from cgroup `memory.events` and the RSS
> slope instead. Recorded here so it is not silently lost.

> [!important] The governor is a measurement-validity problem, not just a latency one
> `scaling_cur_freq` read **1.6 GHz**, not 2.4 GHz — `ondemand` had clocked down at idle. A
> "% of one core" figure taken at a varying clock is **not comparable across runs**, so every CPU
> number in this campaign is ambiguous until the clock is pinned.
>
> This is a second, independent reason to switch to the `performance` governor proposed in
> [[Pi Setup Plan]] — the first was latency jitter. The matrix must run on one governor, recorded,
> and never changed mid-campaign.

## Work packages

| WP | What | Route | Status |
|---|---|---|---|
| 0a | Relax Python pin to `>=3.11`, add `verify-py313` | me | ✅ **done** |
| 0b | Pi venv + runtime deps | me | ✅ **done** — scipy 1.18.1 + bleak wheels exist for cp313/aarch64 |
| 0c | Import-cost baseline | me | ✅ **done** — see above |
| 1 | `PacketTracker` signed step + sessions (fixes P0-B) | agy (worktree) | ✅ **merged, P0-B verified fixed on hardware** |
| 2 | Loss accounting + post-reset rebasing (fixes P0-A) | chain A | running |
| 3 | Single publish + injectable clock | chain A | running |
| 4 | State machine `WARMUP/VALID/DEGRADED/STALE` + time-driven loop | chain A | running |
| 5 | Robustness guards + `SessionHealth` | chain A | running |
| 6 | Waveform + fault generator | agy (worktree) | ✅ **merged** |
| 7 | Shared `_FramePump` + `SocketSampleSource` | chain B | pending |
| 8 | `tools/mock_wearable.py` | chain B | pending |
| 9 | `FakeBleakClient` tests | Sonnet | ✅ **merged** |
| 10 | `--source` CLI + fusion probe + systemd unit | chain B | pending |
| 11 | `make_dummy_model.py` | Sonnet | ✅ **merged** |
| 12 | `benchmark_pi.py` rewrite | pending | pending |
| 13 | Execute matrix + `docs/EVIDENCE.md` | pending | pending |
| **14** | **Drop scipy (conditional)** | conditional on WP-12 RSS | costed, not started |

### Current verified state on the Pi (merged main)

```
54 passed                                  # was 26 at session start
ruff: All checks passed!
mypy: Success: no issues found in 13 source files
BIDMC hr_mae_bpm: 0.5049918437361341       # bit-identical across every change
simulate CLI: exit 0
```

**P0-B proven fixed on hardware** by direct reproduction:

| Scenario | Before | After |
|---|---|---|
| MCU reset packet | `sample_gap = 4,294,607,276` | `0`, new `session_id` |
| Backwards rollback (FIFO re-read) | ~4.29e9 | `0` |

### Process notes worth keeping

> [!warning] Four concurrent Docker builds starved the agents
> I launched the main verify plus two agy worktree verifies plus a 3.13 build at once. scipy is a
> 34 MB download at ~300 kB/s, so the builds contended on bandwidth and deadlocked; one agy job gave
> up and fell back to a host Python 3.14 venv. **Fix: the Pi is now the primary verification
> environment** — no image build, and it is the actual target. Docker 3.11 stays as the reference
> for byte-equality assertions only.

> [!important] The type gate was not reproducible across environments
> Docker (mypy 1.20.2 / numpy 2.4.6) passed code that the Pi (mypy 1.15.0 / numpy 2.2.4) rejected
> with three errors — a bare `np.ndarray` return and two `max()` calls mixing `float` with
> `floating[_32Bit]`. All three were genuine imprecision. Fixed; BIDMC output was bit-identical
> afterwards, confirming the change was behaviour-neutral.

> [!note] A brief defect caught by the ledger discipline
> My Chain A brief assigned the decode guard (5.1/5.2) to an agent that does not own
> `acquisition.py`, where `PacketCodec.decode` actually lives — while the plan places it in WP-7's
> `_FramePump`. A double-assignment like that is precisely how a requirement ends up dropped by both
> parties. Corrected mid-flight by messaging the agent with a revised seam: the service reads
> transport counters through an optional `health()` protocol that WP-7 will implement.

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

---

## Resume here (2026-08-28, end of session)

### State
`main` is **clean and fully verified on the Pi** at commit `241a7de`: 54 tests, ruff clean, mypy
clean, BIDMC `hr_mae_bpm` 0.5049918437361341. Nothing unverified was merged.

Branch **`wp2345-chain-a-wip`** holds Chain A (WP-2..5) — schema v2, the
`WARMUP/VALID/DEGRADED/STALE` states, injectable clock + `FrameWaiter`, `SourceHealth` protocol,
`BoundedOutputSink`, and virtual-time helpers in `conftest.py`.
**It is UNVERIFIED** — the agent was killed by a session rate limit mid-task and the Pi went
unreachable before the gate could run. Do not merge until the full gate passes on hardware.

### Why work stopped
1. Both delegated agents died on `rate_limit` (session limit, resets 00:00 Africa/Cairo).
2. The Pi dropped off the network — absent from ARP, `tailscale` shows it offline. The laptop had
   also fallen back to an APIPA `169.254.x.x` address, and the gateway ping was ~1.3 s, so the local
   network was degraded generally. Not something the campaign caused.

### First three things to do next session
1. Reach the Pi (`ssh -i ~/.ssh/id_ed25519 khalifa@192.168.100.181`). If it does not answer, a
   power-cycle is safe — nothing was mid-write to its filesystem.
2. Run the gate on `wp2345-chain-a-wip`, then verify against ledger items 2.1-2.5, 3.1-3.5,
   4.1-4.9, 5.1-5.9 **against the plan, not the agent's report**.
3. Dispatch WP-7/WP-8 (Chain B) — briefed but never started. `acquisition.py` and
   `tools/mock_wearable.py` are disjoint from Chain A's files, so they can run in parallel.

### Delegation lesson for next time
Claude-model subagents burn the same session quota as the main loop, so a long campaign exhausts it.
Route implementation to **agy** (`gemini-3.1-pro-high` is the strongest available; `agy models`
lists the rest) and use **codex** for review — both draw on separate quotas. Keep orchestration
turns short.

### Pi offline — 2026-08-28 late session

The Pi dropped off the network and did not return. It is unreachable by **every** route tried:

| Route | Result |
|---|---|
| LAN `192.168.100.181` | TCP 22 refused, ping fails (`Test-NetConnection`: both false) |
| Tailscale `100.113.107.122` | **offline, last seen 6h ago** |
| mDNS `raspberrypi.local` | does not resolve (Windows has no Bonjour) |
| MagicDNS `raspberrypi` | resolves to the Tailscale IP, connection times out |

A sweep of `192.168.100.100-200` found three hosts, **none with a Raspberry Pi MAC**
(`b8:27:eb` / `dc:a6:32` / `e4:5f:01` / `d8:3a:dd` / `2c:cf:67`), so `.181` is now held by a
different device on a reassigned lease.

**Needs physical attention**: check the Pi's power and Ethernet. It cannot be recovered remotely.
Nothing was mid-write to its filesystem, so a power-cycle is safe.

**Consequence:** the hardware gate is blocked. Docker (Python 3.11, x86_64) is the interim gate, and
it is **not the target** — every result recorded while the Pi is down must be labelled
**not hardware-verified**.

> [!tip] Give the Pi a DHCP reservation
> Its address has now moved twice. Pin `192.168.100.181` to the Pi's MAC in the router, or set a
> static address. An address that moves mid-campaign silently invalidates every scripted run.

### Chain A gate result — 5 failures, do not merge

`docker compose run --rm verify` on `wp2345-chain-a-wip`: **5 failed, 71 passed**. The failures are
in the agent's *own* new tests, which is the good outcome — it wrote tests that catch its unfinished
work before a human did:

- `test_valid_degrades_on_loss_then_recovers`
- `test_sensor_fault_marks_the_whole_window_not_one_packet`
- `test_packet_loss_fraction_is_a_rolling_window`
- `test_frame_driven_path_matches_the_time_driven_path`
- `test_session_block_reports_all_ten_fields` — `sequence_gaps` reports 0 where 5 is expected

This confirms holding it off `main` was correct. Ledger items 2.4 (rolling loss window), 4.5 (sticky
sensor status), 4.8 (frame-driven parity), and 5.9 (the ten-field session block) are the ones still
open.

---

## Milestone — the mock-ESP32 rig works end to end

2026-08-29. WP-7 + WP-8 merged (`247aaf5`). Synthetic PPG → wire-format encode → TCP → decode →
`PacketTracker`, all in one run:

```
frames decoded      : 400
samples/packet      : 3          <- MTU-realistic default, not the old 20
first seq/index     : 0/0
last  seq/index     : 399/1197
sequence gaps       : 0
elapsed             : 9.63s -> 41.5 packets/sec
health              : {'packets_received': 400, 'decode_errors': 0,
                       'queue_depth': 0, 'queue_high_water': 2, 'dropped_frames': 0}
stream contiguous   : True
```

`last_index == first_index + (n-1) * sample_count` holds exactly, so nothing was dropped, reordered,
or silently fabricated across the transport. **This is the "we act as the ESP32" capability the
campaign was built for** — minus the radio, which no available hardware can provide.

> [!warning] Not hardware-verified
> This ran in the Docker Python 3.11 reference container on x86_64, **not on the Pi**, which is
> offline. Throughput and latency figures from a container are not Pi figures. The rig is proven to
> *work*; its performance numbers still need the real target.

### What the rig now gives us

- `_FramePump` shared by `BleakSampleSource` and `SocketSampleSource`: bounded queue (drop-newest,
  counted), decode guard so one malformed packet no longer kills the service, and a `health()`
  protocol (`packets_received`, `decode_errors`, `queue_depth`, `queue_high_water`,
  `dropped_frames`).
- The socket reader is **independently driven**, so TCP's kernel flow control cannot mask the
  overflow the bounded queue exists to guard against. The earlier demo showed 34 packets received
  while only 10 had been consumed — proof the reader runs ahead of the consumer.
- `tools/mock_wearable.py` with `--mtu` (default 3), BLE-style 30 ms connection-interval bursting,
  jitter, `--disconnect-at` / `--reconnect-after`, `--firehose`, and a `perf_counter_ns` sidecar CSV
  for end-to-end latency joins.
- The two TODO tests that documented the old defects are retired and now assert correct behaviour.

### P0-A demonstrated empirically on `main`

Previously P0-A was established by reading the code. It is now reproduced as a measurement, using
the WP-6 generator to build a 200 s stream with a genuine MCU reset injected at the halfway point
(status `SENSOR_RESET`, sample index restarting at 0 **and continuing from there**, as real hardware
behaves):

```
CLEAN : 240 outputs
RESET : 120 outputs   (reset injected at packet 500 = t+100s)
OUTPUTS LOST TO THE RESET: 120  (50% of the run)
```

The service emitted **nothing at all for the entire 100 seconds following the reset** — exactly the
predicted failure. In a real vehicle a wearable reset one hour into a drive would blind the
physiological channel for an hour, while the system continued to report as if healthy.

> [!note] A first attempt at this demo failed, and the failure was mine
> The initial version injected the reset as a single-packet blip and let the sample index jump
> straight back to its old value. Nothing reproduced, and it would have been easy to record that as
> "P0-A not confirmed". A real reset restarts the index at 0 and *continues* from there; once the
> stream was modelled correctly the defect appeared immediately and exactly. **A negative result
> from a test that does not model the failure is not evidence of absence.**

Fixed by WP-2 on `wp2345-chain-a-wip` (not yet merged — that branch still has 5 failing tests).

---

## Matrix A — first accuracy evidence against generator ground truth

Run on merged `main` in the Docker 3.11 reference. The WP-6 generator emits ground-truth beat
indices, so HR can be scored against truth rather than against itself.

| Scenario | Truth beats | Outputs | Mean HR | Expected | Error |
|---|---:|---:|---:|---:|---:|
| A1 clean 60 bpm | 180 | 144 | 60.01 | 60.0 | **0.01** |
| A1b clean 75 bpm | 225 | 144 | 75.00 | 75.0 | **0.00** |
| A3 batch=3 (ATT MTU 23) | 180 | 142 | 60.00 | 60.0 | **0.00** |
| A3 batch=7 | 180 | 138 | 60.00 | 60.0 | **0.00** |
| A3 batch=20 (old simulator) | 180 | 144 | 60.01 | 60.0 | **0.01** |
| A3 batch=79 (MTU 247) | 180 | 98 | 60.05 | 60.0 | **0.05** |
| A4 drift + noise (σ=300) | 180 | 144 | 60.01 | 60.0 | **0.01** |
| A2 ramp 50→120 bpm | 255 | 144 | 85.18 | 85 (ramp mean) | — |

Ground-truth beat counts are exactly right in every case (180 beats in 180 s at 60 bpm; 225 at
75 bpm), which validates the generator itself as well as the detector.

> [!success] The MTU risk does not damage accuracy
> This was the open question from the MTU analysis. Across a **26× sweep in packet size (3 → 79
> samples)** the HR error stays at or below **0.05 bpm** — far inside the ≤3 bpm gate in
> `VALIDATION.md:52`. Peaks straddling packet boundaries are neither double-counted nor missed at
> any realistic MTU.
>
> That closes the *correctness* half of the MTU risk. The **cost** half is still open: batch=3 means
> ~6× more `find_peaks` calls per second, and that CPU measurement needs the Pi.

Note A2's 85.18 bpm is the correct answer, not an error: it is the mean of a linear 50→120 ramp.

---

## Fault matrix — one safety invariant holds, one new P0 found

Eight fault types injected through the WP-6 generator on merged `main`:

| Scenario | Output states | Quality reasons raised | Fatigue leak |
|---|---|---|---|
| A5 motion burst | warmup 72, good 45, **bad 99** | CLIPPING, ARTIFACTS, INSUFFICIENT_BEATS | **0** |
| A6a clipping | warmup 216 | CLIPPING, ARTIFACTS, FLATLINE | **0** |
| A6b flatline | warmup 216 | ARTIFACTS, FLATLINE | **0** |
| A6c contact loss | warmup 216 | **SENSOR_FAULT**, CLIPPING, FLATLINE | **0** |
| A6d saturation | warmup 72, **bad 144** | CLIPPING, ARTIFACTS | **0** |
| A11 FIFO overflow | warmup 72, **bad 144** | **SENSOR_FAULT**, ARTIFACTS | **0** |
| A7 packet loss 5% | warmup 216 | **PACKET_LOSS**, ARTIFACTS | **0** |
| A9 sequence wraparound | warmup 72, **good 144** | ARTIFACTS | **0** |

> [!success] The core safety invariant holds
> **`fatigue_leak = 0` in every single scenario.** Not once did a fatigue probability escape while
> quality was BAD. That is the invariant the whole "models report, fusion decides" boundary rests on
> ([[Models Index#Architectural principles]]), and it is now tested against eight distinct fault
> types rather than assumed.

> [!success] A9 — sequence wraparound is clean
> 144 good outputs across the 65535 → 0 boundary with **no PACKET_LOSS reason raised**. No false
> loss event, exactly as `VALIDATION.md:36` requires.

### P0-C (NEW) — any packet loss wipes the entire 60-second interval history

**A7 is the alarming row.** With 5% packet loss the service produced **no heart rate at all** — 216
outputs, every one stuck in `warmup`. Root cause, confirmed at `service.py:69-71`:

```python
if observation.sample_gap or observation.reset_detected:
    self._lost_samples += observation.sample_gap
    self._reset_signal_state()      # -> self._intervals.clear()
```

**Any** gap, however small, clears the *entire* accumulated interval deque. At batch 20 a 5% loss is
a gap roughly every 4 seconds, so a 60-second feature window can never fill. PRV becomes permanently
unobtainable.

This violates the subsystem's own specification. `ARCHITECTURE.md:116` requires: *"reset only
affected detector state when needed, and degrade or reject the affected window"* — not discard all
history. And `ARCHITECTURE.md:108` lists packet loss as a **normal operating condition**, which BLE
guarantees will occur.

**Severity: P0.** Alongside P0-A and P0-B this is the third way the subsystem fails under conditions
its own documentation calls normal. Unlike those two it was found by *measurement*, not by reading —
no amount of code review had surfaced it.

**Fix direction:** on a gap, reset the filter/detector continuity (correct — the waveform really is
discontinuous) but *retain* intervals outside the gap, marking only the spanning interval invalid.
Tracked as **WP-15**.

> [!note] Why A6a-c sit in `warmup` rather than `bad`
> Clipping, flatline, and contact loss destroy the signal so completely that no valid intervals ever
> form, so `extract_features` returns `None` and the state string stays `warmup`. The quality reasons
> are raised correctly and fatigue is correctly suppressed, so this is not a safety failure — but it
> is the `WARMUP`/`BAD` vocabulary confusion that WP-4 exists to fix. A consumer cannot currently
> distinguish "still starting up" from "sensor destroyed".

---

## Independent review of Chain A (codex, high reasoning)

Codex reviewed `wp2345-chain-a-wip` against all 23 ledger items and hunted adversarially for bugs
the checklist would miss. It ran the code, not just read it — it constructed a `SilentSource` and a
`StopSink` to probe the state machine directly.

**Requirement table:** 16 IMPLEMENTED, 3 PARTIAL (4.4, 4.8, 5.6-5.8), 2 WRONG (4.3, 4.6).

### The two P1s — both "fails silently while looking healthy"

> [!danger] P1 — a dead sensor at boot never becomes STALE
> `service.py:162`. The timeout path passes `stale=False` until a frame has *already* arrived, so a
> sensor that never connects sits in `WARMUP` **forever**. Fusion cannot distinguish "still warming
> up" from "the wearable was never plugged in" — and WARMUP is not an alarming state, so nothing
> escalates.

> [!danger] P1 — a wrong-rate source suppresses stale detection entirely
> `service.py:202`. Mismatched-rate frames refresh `_last_frame_ns` **before** being dropped, so a
> misconfigured source keeps `last_frame_age_seconds` near zero while discarding every single
> packet. The service reports a healthy, recent frame age while producing nothing.

Both are exactly the failure class the review was asked to hunt: **silently wrong rather than loudly
broken**, which in a driver-monitoring context means the physiological channel is dead while the
system believes it is fine.

### P2s

- `service.py:166` — time-driven mode leaks queue occupancy into the payload, so `time_driven=False`
  cannot byte-match it (breaking the 4.8 parity requirement); `queue_high_water` is also sampled
  *after* dequeue, so it under-reports peak depth.
- `service.py:199` — `run()` still awaits arbitrary sinks directly; only the CLI wrapper installs
  `BoundedOutputSink`, so a raw sink exception can still escape into acquisition. 5.6-5.8 is
  therefore only PARTIAL.

### The finding that changes the plan

> [!important] Four of the five failing tests are **test-data bugs, not source regressions**
> `tests/conftest.py:94` and four cases in `test_service_states.py`: the gap helper slices past the
> end of a 450/1000-packet run, and the 90-second fault case leaves only ~20 s after the fault —
> less than the 60 s feature window needs.
>
> This matters because the obvious reading of "5 failing tests" is "the source is broken", and an
> agent told to make them pass could easily have contorted working source to satisfy a broken
> fixture. An independent reviewer that *runs* the code caught what a checklist could not. Chain A
> was briefed to justify any test change rather than silently weaken one — its justification now has
> a second opinion to be checked against.

---

## A19 — 30-minute soak: no leak, all buffers bounded

9,000 packets = 30 minutes of 100 Hz data with drift and noise, replayed through merged `main`.
The sink counts rather than accumulates, so the known unbounded-`InMemorySink` defect cannot
masquerade as a service leak.

```
outputs           : 2160   states={'warmup': 72, 'good': 2088}
RSS start/end     : 120.7 -> 123.9 MB  (delta +3.2)
RSS slope (steady): +0.00 MB over the measured span
intervals deque   : max 62 (bounded)
raw ring buffer   : max 12000 samples (cap 12000)
cadence           : 2160 outputs for ~1740s post-warmup -> 1.24/s
```

> [!success] Memory is genuinely bounded
> **Steady-state RSS slope is +0.00 MB.** The +3.2 MB total is startup allocation, not growth. The
> interval deque tops out at 62 entries and the raw ring buffer sits exactly at its 12,000-sample
> cap — both bounded by construction, now confirmed by measurement over 1.8 million samples.
>
> This satisfies `VALIDATION.md:91-97` (no backlog, bounded ring buffers, no RSS growth after
> warm-up) for the processing path. Cadence of 1.24/s matches the expected ~1 HR/s plus periodic
> feature emissions.

RSS here is 121-124 MB against the 120 MB target — slightly above, versus ~108 MB measured on the
Pi. The container carries more baseline than the Pi does, so the Pi figure is the one that counts,
and it remains the honest number. Either way the story is unchanged: **the memory is scipy's import
footprint, not the service's working set.**

---

## B3 — firehose overflow through the real socket rig

`mock_wearable.py --firehose` against a deliberately throttled consumer (4 ms per frame), so the
transmitter outruns the reader by ~33×:

```
frames consumed     : 121 (consumer throttled to 4ms/frame)
health              : {'packets_received': 4000, 'decode_errors': 0,
                       'queue_depth': 0, 'queue_high_water': 64, 'dropped_frames': 3879}
gap events seen     : 55   samples accounted lost: 11565

queue bounded       : True  (high_water=64, cap 64)
decode errors       : 0
HONEST DEGRADATION  : True
```

> [!success] Bounded, counted, and honest under 33× overload
> - **`queue_high_water == 64`, exactly the cap.** The queue never grew past its bound, which is the
>   whole point of WP-7 and what `VALIDATION.md:94` demands.
> - **`decode_errors == 0`.** Dropping under pressure did not corrupt the stream — no partial or
>   misaligned packet ever reached the codec.
> - **Drops surfaced downstream as genuine counted gaps**: 3,879 dropped packets × 3 samples ≈
>   11,637, against 11,565 samples the `PacketTracker` independently accounted as lost. The two
>   numbers agree to within the packets still in flight.
>
> That last point is the requirement that matters (7.7). A system under overload that silently
> produced *plausible but wrong* heart rates would be far more dangerous than one that reports
> degradation. It degrades honestly.

This also validates the WP-7 design note: because the socket reader is **independently driven**, TCP's
kernel flow control did not mask the overflow. A naive read-then-yield loop would have shown
`dropped_frames: 0` here and proven nothing.

---

## Merged main — P0-A fixed, P0-C corrected to STILL OPEN

All work packages merged (`5a51a80`). **80 tests pass**, ruff and mypy clean.

### P0-A — fixed, measured

```
P0-A  clean=200  reset=200  lost=0        (was losing 120/240 = 50%)
P0-A  HR outputs after reset present: True
```

An MCU reset now costs **zero** outputs, against 120 lost before. The service resumes heart-rate
output after the reset instead of falling silent for the rest of the run.

(The clean-run count moved 240 → 200 because WP-3 removed the double publish. Fewer outputs here is
the fix, not a regression.)

### P0-C — I called this fixed. It is not.

A first check at one loss rate reported "P0-C FIXED", and I nearly recorded that. A sweep across
loss rates shows the real picture:

| Loss pattern | Outputs | With HR | HR yield |
|---|---:|---:|---:|
| none | 200 | 140 | **70%** |
| gap every 40 packets (2.5%) | 203 | 80 | **39%** |
| gap every 20 packets (5%) | 203 | 20 | **10%** |
| gap every 10 packets (10%) | 201 | 18 | 9% |
| gap every 5 packets (20%) | 200 | 17 | 8% |
| gap every 3 packets (33%) | 197 | 15 | 8% |

> [!danger] P0-C remains open — 5% packet loss still collapses HR availability 7×
> The root cause is untouched. `service.py:217-218` still calls `_reset_signal_state()` on **any**
> `sample_gap`, and that method still ends with `self._intervals.clear()` (line 245) — discarding
> the entire accumulated interval history for a gap of a single packet.
>
> What the merge changed was the *symptom*: the rolling loss window and emit-index rebasing let some
> HR through between gaps. HR yield still falls from 70% to **10%** at 5% loss — a rate BLE will
> routinely exceed.
>
> `ARCHITECTURE.md:116` requires resetting *"only affected detector state"* and rejecting *"the
> affected window"*, not the whole history. **Tracked as WP-15, still open.**

> [!warning] How the wrong conclusion nearly got recorded
> The first check used one loss configuration and a hand-built frame stream; it showed HR present
> and printed FIXED. The sweep used the generator's own loss injection across six rates and showed
> a 7× collapse. **A single passing data point is not a fix**, and "the symptom went away at the one
> setting I tried" is the easiest way to close a defect that is still there.

### Two P1s from the codex review, both fixed with regression tests

- **A sensor that never connects** now reports `STALE` instead of sitting in `WARMUP` forever
  (`_emit_tick(stale=True)` on every timeout — a timeout *is* staleness).
- **Wrong-rate frames** no longer refresh the freshness timestamp before being discarded, so a
  misconfigured source can no longer hold `last_frame_age_seconds` near zero while dropping
  everything.

### Still open, honestly

- **WP-15 / P0-C** — interval history discarded on any gap (above).
- **Ledger 5.6-5.8 PARTIAL** — `BoundedOutputSink` is installed only by the CLI wrapper, so a raw
  sink passed directly to `PhysiologyService` can still raise into acquisition.
- **Nothing here is hardware-verified.** The Pi is offline; all of this is the Docker x86_64
  reference.

---

## Optimisation options assessed — ONNX is the wrong tool here

The question was whether ONNX Runtime (or similar) would help this subsystem on the Pi. **It would
make it worse**, and it is worth writing down why, because the reasoning is not obvious.

### Why ONNX does not apply to physiology

| | |
|---|---|
| **What the model is** | Logistic regression over **7 features**. Inference is 7 multiply-adds and one sigmoid. |
| **How it runs today** | A JSON artifact loaded at startup, scored in plain Python/numpy. `docs/ARCHITECTURE.md:124` deliberately forbids unpickling a scikit-learn object at runtime. |
| **Its current cost** | Effectively zero — unmeasurable against the 5 MB working set. |
| **What ONNX Runtime would add** | Tens of MB of runtime library, a new native dependency chain on aarch64, and a graph executor. |

ONNX exists to make **neural network graphs** portable and fast. Applying it to a 7-parameter linear
model imports an execution engine to do arithmetic that is already free. It would consume budget in
exactly the dimension that is already tight (memory), to accelerate the one component that costs
nothing.

**Verdict: reject for physiology.** Not a close call.

### Where ONNX *is* relevant to RTDMS

The two vision models ([[Models Index]]) are a genuinely different case — real CNNs where graph
optimisation and quantisation matter. But note the target: those run on the **Hailo AI HAT+**, whose
runtime consumes compiled `.hef` files, not ONNX. There ONNX is a **conversion format on the path**
(PyTorch/TF → ONNX → Hailo Dataflow Compiler → `.hef`), not the thing executing on-device. Worth
recording now so nobody later installs `onnxruntime` on the Pi expecting it to drive the accelerator.

### The optimisation that actually pays — WP-14

The real inefficiency is not the model, it is a **library import**:

| Import set | RSS |
|---|---:|
| Bare Python 3.13 | 8.9 MB |
| + numpy | 22.6 MB |
| **+ scipy.signal** | **99.6 MB** |
| + bleak (full runtime) | 103.1 MB |

**scipy costs 77 MB for exactly three function calls** — `butter`, `sosfilt`, `find_peaks` — all in
`signal.py`. The service's own working set is about 5 MB. Removing scipy takes the floor from
~103 MB to ~26 MB, turning a gate we barely pass into one we pass four times over.

> [!warning] Guarded by an equivalence proof, not by hope
> Peak detection is where the documented 0.50 bpm BIDMC accuracy comes from. WP-14 is therefore
> gated on a hard proof: the numpy filter must match `scipy.signal.sosfilt` to 1e-6 across batch
> boundaries, and the numpy peak detector must return **identical index arrays** to
> `scipy.signal.find_peaks` on five varied signals. If the detector cannot be made to match exactly,
> the instruction is to **stop and keep scipy**. A memory saving bought with accuracy is not a
> saving.

### Options considered and rejected

- **ONNX Runtime** — rejected above.
- **Quantisation / INT8** — meaningless for 7 float coefficients.
- **TFLite / tflite-runtime** — same objection as ONNX, plus another dependency.
- **Hailo offload for physiology** — the accelerator is for vision; a linear model would not benefit,
  and the PCIe slot is contested ([[Pi Setup Plan#Blocker 2 — The PCIe contention problem]]).
- **numpy replacement of the three scipy calls** — **selected.** Largest measured win, no new
  dependency, and verifiable by direct equivalence against the thing it replaces.

## WP-14 executed then reverted; WP-15 confirmed as a real, partial win

WP-14 (drop scipy from `signal.py`, replace with pure numpy) was implemented by an agy job and
initially accepted: the equivalence proof held (max filter deviation 1.47e-08, peak indices
identical on five synthetic signals), and BIDMC still reproduced closely (0.5075 vs 0.5082 bpm MAE,
same 420 outputs).

**Then it was reverted (`987b24b`).** Two things the agent's own report never surfaced, because
its brief only required the equivalence proof and a BIDMC check, not a real-MTU CPU measurement:

- **CPU regression.** At the realistic batch=3 MTU, CPU went from **1.97% to 3.27%**, over the 2%
  hard gate. `sosfilt`'s C implementation is not something numpy can vectorise away — an IIR filter
  is inherently sequential, one sample depends on the last, and a pure-Python per-sample loop pays
  for every one of those dependencies. scipy's ~30 MB RSS cost buys real speed, not just convenience.
- **A silent constructor bug**, found by direct code inspection, not testing: the numpy
  `StreamingBandpass.__init__` accepted `sample_rate_hz`/`lowcut_hz`/`highcut_hz` but silently
  ignored them, hardcoding fs=100 SOS coefficients. It "worked" only because every test in the repo
  happens to use 100 Hz data — it would have silently misfiltered BIDMC's real 125 Hz signal, except
  a separate regression (below) was masking BIDMC entirely at the time.

Reverted in full: `signal.py` and `pyproject.toml` back to scipy, the equivalence test removed.
WP-15 (independent, service.py-only) was kept — it doesn't touch the filter/peak-detector path.

### A regression this campaign shipped, found by re-checking BIDMC after the revert

While isolating whether WP-14 broke BIDMC, `validate_bidmc.py` failed with `RuntimeError("the
replay produced no quality-gated HR outputs")` — on WP-14, and then, checked directly, **on plain
`main` too**. Root cause: Chain A's merge (`5a51a80`) introduced schema v2's uppercase
`STATE_VALID`/`STATE_DEGRADED` state vocabulary, but `validate_bidmc.py` still filtered on the old
lowercase `"good"`/`"degraded"` strings, so every output was silently discarded. This had been
merged to `main` and left there without re-running the BIDMC check the delegation brief for that
work had actually required. Fixed in `40a47e7`; new baseline `0.5082470420003504 bpm MAE`, 420
outputs (504→420 is WP-3's fixed double-publish, not a new problem) — recorded in
`docs/EVIDENCE.md`.

### P0-C re-measured after WP-15 — meaningfully better, still not closed

The original discovery-time sweep (`70%→10%` HR yield at 5% loss) used a different config than what
survives in the repo and cannot be reproduced exactly; the number below is a fresh, reproducible
run against current `main` (`packet_loss_indices`, batch=20, 120 s, seed=5):

```python
# tools/verify_on_pi.sh-style inline check, run with PYTHONPATH=<checkout>/src
from dms_physiology.waveform import WaveformConfig, generate_ppg
cfg = WaveformConfig(seconds=120.0, batch_size=20, seed=5,
                      packet_loss_indices=tuple(i for i in range(400) if i % every == 0))
```

| Loss | Outputs | With HR | HR yield |
|---|---:|---:|---:|
| none | 120 | 60 | 50.0% |
| 2.5% | 120 | 60 | 50.0% |
| 5% | 120 | 60 | 50.0% |
| 10% | 120 | 38 | 31.7% |
| 20% | 120 | 37 | 30.8% |
| 33% | 127 | 42 | 33.1% |

**WP-15 genuinely helps.** Yield no longer collapses at 5% loss — it matches the clean baseline
exactly. The degradation now starts at 10%+ and plateaus around 31–33% instead of continuing to
fall toward zero. It is still a real gap (roughly 20 points below baseline at 10%+, and
`ARCHITECTURE.md:116`'s "only the affected window" is only partially honoured) — not closed, but no
longer the near-total collapse it was at discovery.

## The Pi went offline, then came back — 2026-08-29

The Pi became unreachable across LAN IP, Tailscale IP, and MagicDNS hostname for an extended period
while the user was away from home, prompting a direct question about physical damage. The answer,
based on evidence rather than guesswork: **no indication of damage.** Last known-good telemetry
before the outage was clean (45.2°C, `throttled=0x0`, no thermal/voltage fault ever recorded across
the whole campaign), and a Pi 5 throttles and flags well before anything resembling real damage. The
symptom pattern — dropped off SSH *and* ping *and* Tailscale roughly together, with the user's own
Tailscale client separately showing coordination-server health problems — pointed at a mundane
network/power interruption, not hardware failure.

**It reconnected on its own.** `uptime` on reconnect showed the Pi had been up only ~5 minutes,
confirming a reboot (crash, power blip, or a power cycle) rather than damage.

### Full hardware verification, re-run end to end

`tools/verify_on_pi.sh 192.168.100.181`, 2026-08-29, governor `ondemand`, boot device
`/dev/mmcblk0p2` (microSD):

```
== environment ==
raspberrypi  aarch64  Python 3.13.5
temp: 47.7°C -> 51.6°C after load   throttled=0x0 (both)

== gate ==
pytest: 81 passed (3 async resource warnings — un-awaited pump.aclose() in
        test_socket_source_health, and "Event loop is closed" GC noise from
        test_property_codec_roundtrip; both pre-existing test hygiene, not failures)
ruff:   All checks passed!
mypy:   Success: no issues found in 13 source files

== BIDMC ==
hr_mae_bpm: 0.5082470420003504   evaluated_outputs: 420   (matches Docker exactly)

== CPU and RSS, MTU sweep ==
  batch=3  (ATT MTU 23, realistic)   1.31% CPU   108.5MB RSS
  batch=20                            0.22% CPU   109.6MB RSS
  batch=79 (MTU 247)                  0.08% CPU   109.7MB RSS
```

This closes the last open item this campaign was scoped to close: real-hardware CPU/RSS at the
realistic MTU. All three MTUs land inside the 2%/150MB hard gates; only batch=3's CPU sits above
the 1% *target* (1.31%), consistent with the expectation that real BLE (D-Bus marshalling, not
measured here) will cost more than this TCP-rig lower bound, but with headroom to absorb it.

`docs/EVIDENCE.md` has been updated to reflect all of the above as the current, hardware-verified
state. **Nothing here required a second connectivity outage or a rebuild** — the sync-and-verify
script written earlier in the campaign for exactly this scenario worked on the first try once the
Pi answered SSH again.

## Closing the last real gap — the live two-process rig, genuinely on the Pi

Every prior "end-to-end" claim, including the "Milestone — the mock-ESP32 rig works end to end"
section above and the first Pi resource measurements, actually fed pre-generated frames straight
into `PhysiologyService` **in-process** (`ReplaySource` or a hand-built frame list) — never through
an actual live socket, and never with `mock_wearable.py` running as a genuinely separate process.
The one run that *did* use a real TCP connection between two processes was Docker-only and
explicitly flagged "not hardware-verified." So despite the Pi runs above, the literal "we act as
the ESP32, send it data, the Pi computes" loop had never been exercised on target.

Closed it directly: launched `tools/mock_wearable.py` as an independent background process on the
Pi (`--mtu 3`, realistic packet size, `--seconds 75`), and a second process constructing the real
`SocketSampleSource` + `PhysiologyService` + `InMemorySink`, connecting to it over `127.0.0.1:8124`.

```
elapsed 60.03s
health {'packets_received': 2500, 'decode_errors': 0, 'queue_depth': 0,
        'queue_high_water': 2, 'dropped_frames': 0}
outputs 88   state sequence: WARMUP -> VALID
last mean_hr_bpm 60.0
session {'packets_received': 2483, 'decode_errors': 0, 'duplicates': 0, 'reordered': 0,
         'sequence_gaps': 0, 'dropped_outputs': 0}
outputs with a real HR number: 18, e.g. [60.033, 60.033, 60.032, 60.031, 60.0]
```

2,500 packets over a live socket, zero decode errors, zero dropped frames, zero duplicates/
reordered/gaps — and the state machine correctly held `WARMUP` for the full 60 s `feature_window`
before transitioning to `VALID` with `mean_hr_bpm=60.0`, matching the transmitted signal exactly.
(An earlier 30 s attempt correctly stayed in `WARMUP` the whole run and reported no HR — expected,
not a bug: `feature_window_seconds=60.0` by design, so 30 s of transmission cannot leave warmup.)

This is now genuinely proven on target: the wire protocol, the socket transport, the bounded queue,
the packet tracker, the state machine, and the HR pipeline, all exercised together, live, on the
Raspberry Pi's own CPU. `service:main` still has no `--source tcp` flag (WP-10, never implemented),
so this remains a wiring script rather than the shipped CLI entrypoint — that gap is unchanged.
