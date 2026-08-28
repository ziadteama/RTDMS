---
title: "Pi Setup Plan — Optimal Configuration"
tags:
  - subsystem
  - hardware
  - setup
  - research
  - decisions
aliases:
  - Pi optimal setup
status: proposed
researched: 2026-08-28
---

# Pi Setup Plan — Optimal Configuration

↑ [[Home]] | Device facts: [[Raspberry Pi 5 Target]] | [[Models Index]]

Research-backed setup for the [[Raspberry Pi 5 Target]], written **2026-08-28**. Where research
contradicts [[5.2 Phase Two Plan|the report]], the better option wins and the divergence is recorded
here.

> [!abstract] The three decisions that actually matter
> 1. **Python 3.13 on Trixie breaks MediaPipe** — the report's primary vision approach. Must choose
>    an OS/runtime strategy before any vision work starts.
> 2. **One PCIe connector, two things want it** — AI HAT+ and NVMe are mutually exclusive.
> 3. **The AI HAT+ and camera do not exist yet** — every CV performance claim is unvalidated.

---

## Blocker 1 — The Python version conflict

Three components want three different Python versions on the same box:

| Component | Requires | Status on this Pi (3.13.5) |
|---|---|---|
| System / Raspberry Pi OS Trixie | 3.13 | Native |
| **MediaPipe** (report's Face Mesh choice, [[2.2 Research Gap]] Table 2-2) | **≤ 3.12**, officially Bookworm only | ❌ **Will not install** |
| [[Physiology Subsystem]] (`dms-physiology`) | `>=3.11,<3.12` | ❌ Pin excludes 3.13 |

MediaPipe has no Python 3.13 wheels — Google's own aarch64 build pipeline ships 3.9–3.12 only, and
MediaPipe is documented as working on Raspberry Pi OS **Bookworm**, not Trixie. Meanwhile Trixie is
where Hailo AI HAT+ support is now first-class (added Dec 2025, installable straight from apt, with
the kernel driver now built via DKMS).

So: the OS that best supports the accelerator is the OS that breaks the vision library.

### Options

| Option | Gets you | Costs you |
|---|---|---|
| **A. Downgrade to Bookworm (Debian 12, Py 3.11)** | MediaPipe works natively; physiology pin satisfied as-is | Older Hailo packaging path; giving up current kernel/firmware; full reflash |
| **B. Stay on Trixie, containerise** | Best Hailo support; each model pinned independently | Docker overhead on a latency-critical box; camera/GPIO passthrough friction |
| **C. Stay on Trixie, drop MediaPipe → run face landmarks on the Hailo** | CPU freed for physiology + fusion; uses hardware already BOM'd; arguably the *correct* architecture | Divergence from report; depends on hardware not yet purchased; more model-porting work |
| **D. Build MediaPipe from source for 3.13** | Keeps report's stack on current OS | Fragile, unsupported, likely recurring breakage |

### Recommendation

**C, with B as the bridge.** Reasoning:

- The whole point of buying a 26 TOPS accelerator is to *not* run vision on the CPU. Running
  MediaPipe Face Mesh on CPU while an idle Hailo sits on the PCIe bus is the wrong shape — and it
  directly threatens [[Physiology Subsystem#Resource budget Pi 5|the physiology CPU budget]]
  (<1% of one core) and the <500 ms end-to-end target in [[3.2 Technical Description]].
- Until the AI HAT+ physically arrives, use **B** (a Python 3.11 container) to make progress on
  MediaPipe-based prototyping without reflashing the OS.
- **D is a trap.** Never build an unsupported wheel for a graded deliverable.
- **A stays viable** as the safe fallback if the Hailo port proves too slow to land before the
  deadline. Decide this at the point the HAT arrives, on measurements — not now.

> [!warning] Do not relax the physiology `<3.12` pin casually
> That pin exists because the package is verified under 3.11. Widening it is a real change requiring
> a full re-run of `docker compose run --rm verify` plus the BIDMC validation. Cheap to do, but it
> must be *done*, not assumed.

---

## Blocker 2 — The PCIe contention problem

The Pi 5 has **one** PCIe FPC connector. Both of these want it:

- **AI HAT+ 26 TOPS** (Hailo-8) — the BOM'd accelerator
- **M.2 HAT+ / NVMe** — the storage upgrade

They are **mutually exclusive** without a stacking/splitter board.

Meanwhile the Pi currently boots from **microSD**, and the research on that is stark:

| Metric | microSD | NVMe | Delta |
|---|---:|---:|---|
| Sequential read | ~90 MB/s | ~858 MB/s | ~10× |
| Sequential write | ~30 MB/s | ~514 MB/s | ~17× |
| Random read IOPS | ~1.5–4 k | ~215 k | **50–100×** |
| Boot time | >45 s | <12 s | ~4× |
| Kernel 6.6 compile | 1 h 58 m | 42 m | 2.8× |

Random IOPS is the number that matters for a CV workload — model loading, dataset reads, and
event logging are all small-random-access patterns.

### Recommendation

**AI HAT+ wins the PCIe slot. Use a USB 3.0 SSD for storage.**

- The accelerator is load-bearing for the project's core claim (real-time multimodal detection on an
  affordable edge device). Storage is a convenience.
- USB 3.0 (5 Gbps) still delivers roughly an order of magnitude better random IOPS than microSD —
  most of the benefit, none of the PCIe conflict.
- microSD also has a **wear** problem this project will hit: continuous event logging plus dataset
  capture ([[3.3 Dataset Selection and Collection]], 10–20 drivers at 1080p30) will chew through
  cards. Card failure mid-demo is a real risk that belongs in
  [[4.4 Feasibility and Risk Analysis]].

> [!tip] Cheapest immediate win
> Move dataset capture and event logs to external storage even before any boot-device change. It
> removes the wear risk and the 57 GB capacity ceiling without touching the boot path.

---

## Blocker 3 — Missing hardware

Per [[Raspberry Pi 5 Target#Hardware gaps]], the **AI HAT+ and camera are not attached**. Until they
are:

- No CV latency figure in [[3.2 Technical Description]] is validated.
- The concurrent Pi benchmark that gates [[Physiology Subsystem]] release **cannot be run at all** —
  it requires both CV models active.
- [[5.2 Phase Two Plan]] Phase 1 and Phase 2 are blocked on procurement, not engineering.

**This is the critical path.** Order the AI HAT+ 26 TOPS and the Pi IR camera 5MP 160° now; every
downstream validation gate is behind them.

---

## Configuration changes to apply

Ordered by value. None applied yet — this is a plan.

### 1. Security updates (do first)

```bash
sudo apt update && sudo apt full-upgrade
```

openssl/libssl3t64 security updates are pending on an SSH-exposed, Tailscale-connected host.

### 2. Enable I2C and SPI

Currently disabled — only the internal HDMI DDC buses exist, no `i2c-1`. Needed for sensor work.

```bash
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
```

Note `[pi5] dtoverlay=nospi10` in config.txt explicitly disables SPI10; leave it unless a peripheral
needs that specific bus.

### 3. CPU governor → `performance`

Currently `ondemand`. Frequency transitions cost 50–100 µs and inject jitter — directly hostile to a
system whose headline requirement is **<500 ms end-to-end with <100 ms trigger delay**.

```bash
sudo apt install cpufrequtils
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
```

Trade-off: higher idle power and heat. The Pi idles at 43.9 °C with no throttling, so there is
thermal headroom — but **re-check `vcgencmd get_throttled` during the thermal soak**, and budget for
active cooling. Throttling during a demo would invalidate every measurement.

### 4. Deterministic latency (measure before applying)

Boot-parameter isolation can cut worst-case latency dramatically (one documented Cortex-A72 case:
600 µs → 18 µs) via `isolcpus` / `nohz_full` / `rcu_nocbs`, pinning the real-time work to a
dedicated core.

> [!warning] Do not apply this blind
> With only 4 cores and three concurrent workloads (2 CV models + physiology + fusion), isolating a
> core may *hurt* aggregate throughput. Establish the concurrent baseline first, then test isolation
> as a change against it. This is an optimisation, not a default.

### 5. Fix the physiology service's deployment shape

[[Physiology Subsystem]] specifies a systemd service with a memory limit and **lower scheduling
priority than the CV models**. Not yet created. Needs `MemoryMax=` and `Nice=`/`CPUWeight=` in the
unit file.

### 6. Consider disabling unused services

`wlan0` is down and unused (wired + Tailscale). Desktop/display stack (`vc4-kms-v3d`,
`display_auto_detect`) is loaded but the deployment is headless. Minor RAM/CPU savings; low priority,
and keep the display stack while it is still a development machine.

---

## Deployment strategy

Recommended shape once hardware lands:

```
systemd
├─ dms-vision-drowsiness.service    (Hailo-accelerated)
├─ dms-vision-distraction.service   (Hailo-accelerated)
├─ dms-physiology.service           (Nice > CV, MemoryMax=150M)
└─ dms-fusion.service               (consumes all three, owns alerts)
        │
        └─ Unix-domain datagram sockets (already the physiology contract)
```

This matches the existing [[Physiology Subsystem#Output contract fusion boundary|output contract]]
and keeps the [[Models Index#Architectural principles|"models report, fusion decides"]] boundary
intact at the process level, not just in code.

---

## Divergences from the report

Per the standing principle that the report is a starting point, not a spec:

| Report says | Plan says | Why |
|---|---|---|
| MediaPipe Face Mesh for eye/gaze/head-pose ([[2.2 Research Gap]] Table 2-2) | Prefer Hailo-native landmark models | MediaPipe has no Py 3.13 support; and CPU inference wastes the BOM'd 26 TOPS accelerator and threatens the physiology CPU budget |
| Silent on storage | USB 3.0 SSD for data, microSD stays boot | microSD random IOPS and write wear are unfit for continuous logging + 1080p30 dataset capture |
| Silent on OS/tuning | Trixie + `performance` governor | Trixie has first-class Hailo support; governor jitter conflicts with the latency requirement |

All three should be reflected in the final report, or defended explicitly in the viva.

---

## Open questions

- **Is the AI HAT+ actually ordered?** Nothing on the Pi suggests it has ever been attached.
- **Cooling solution?** The `performance` governor plus sustained triple-model inference plus a
  thermal soak requirement means passive cooling is likely insufficient. Not costed in
  [[4.5 Cost Calculation and BOM]].
- **Power supply?** `usb_max_current_enable=1` is set; confirm the official 27 W PSU, since an
  under-powered supply plus a HAT plus USB SSD is a classic source of mysterious instability.
- **Does the Hailo model zoo cover face landmarks / gaze well enough** to replace MediaPipe, or does
  a custom model need compiling to `.hef`? This determines whether Option C above is a week or a
  month of work.

## Sources

- [AI HATs — Raspberry Pi Documentation](https://www.raspberrypi.com/documentation/accessories/ai-hat-plus.html)
- [AI software — Raspberry Pi Documentation](https://www.raspberrypi.com/documentation/computers/ai.html)
- [Raspberry Pi OS "Trixie" Gets Hailo AI Kit / AI HAT+ Support — Hackster.io](https://www.hackster.io/news/raspberry-pi-os-trixie-gets-hailo-based-ai-kit-ai-hat-support-and-a-new-ai-camera-feature-5e8523191150)
- [Software updates for Raspberry Pi AI products — Raspberry Pi](https://www.raspberrypi.com/news/software-updates-for-raspberry-pi-ai-products/)
- [Build MediaPipe Python Wheel Package — Google AI Edge](https://ai.google.dev/edge/mediapipe/solutions/build_python)
- [mediapipe — PyPI](https://pypi.org/project/mediapipe/)
- [Raspberry Pi 5 NVMe SSD Setup Guide 2026 — raspberry.tips](https://raspberry.tips/en/raspberrypi-tutorials/raspberry-pi-5-nvme-ssd-boot)
- [NVMe Base review — Raspberry Pi Official Magazine](https://magazine.raspberrypi.com/articles/nvme-base-review)
- [CPU Isolation and Task Affinity for Multicore Optimization](https://ohyaan.github.io/tips/cpu_isolation_and_task_affinity_for_multicore_optimization/)
- [CPU Frequency Scaling — With Raspberry Pi](https://ohyaan.github.io/tips/cpu_frequency_scaling/)
- [Analyzing Real-Time Latency: Interrupt and Scheduling Jitter on Modern ARM Processors](https://howtech.substack.com/p/analyzing-real-time-latency-interrupt)
