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
