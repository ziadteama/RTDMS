# Concurrent pipeline simulation — Pi readiness (no hardware)

**Date:** 2026-09-25  
**Mode:** concurrent processes, no camera / no ESP / no wearable  
**Runner:** `fusion/tools/sim_concurrent_pipeline.py`

## What ran

| Process | Stimulus | Target rate |
|---|---|---|
| `dms-face` | Fixed `portrait.jpg` through MediaPipe FacePipeline | ~15 Hz paced |
| `dms-phone` | Random frames through ONNX `phone_cls.onnx` | ~5 Hz (rate-limited) |
| `dms-physiology` | Synthetic PPG replay, realtime paced | 100 Hz samples |
| `dms-fusion` | `decide()` stub | 10 Hz |

Thread caps: `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`.

---

## A — Laptop host (shape check)

**Host:** Windows 11, Python 3.12, ~20 logical cores, 16.8 GB RAM  
**Artifact:** [`bench_sim.json`](../bench_sim.json) — 25 s

| Model | Achieved Hz | Latency p95 (ms) | CPU % (proc) | RSS (MB) |
|---|---:|---:|---:|---:|
| Face | 14.9 | 10.4 | 13.5 | 114 |
| Phone | 4.7 | 7.9 | 3.9 | 84 |
| Physiology | — (25 outputs; still `WARMUP`) | — | 0.6 | 102 |
| Fusion | 10 | 0.02 | 0.1 | 23 |
| **Sum** | | | **~18** | **~324** |

Physiology `WARMUP` is expected (~60 s valid PPG before `VALID` / HR).

---

## B — Raspberry Pi 5 (authoritative)

**Host:** Raspberry Pi 5 Model B Rev 1.1, Linux aarch64, Python 3.13.5, 4 cores, 8.5 GB RAM  
**SSH:** Tailscale `khalifa@100.113.107.122`  
**Tree:** `~/RTDMS` (lean sync); venv reused from `~/dms-face/.venv` (+ matplotlib, onnxruntime, editable installs)  
**Artifact:** [`bench_sim_pi5.json`](../bench_sim_pi5.json) — 30 s

| Model | Achieved Hz | Latency p95 (ms) | CPU % (proc) | RSS (MB) |
|---|---:|---:|---:|---:|
| Face | **14.79** | **27.1** | **37.1** | **183** |
| Phone (ONNX) | **4.79** | **29.2** | **14.9** | **116** |
| Physiology | 30 outputs (`WARMUP`) | — | **0.6** | **111** |
| Fusion | 10 | 0.02 | **0.1** | **18** |
| **Sum** | | | **~53** | **~429** |

Prior solo face soak (`~/dms-face/bench_pi5.json`): ~49–50 fps full-tilt, ~19 ms mean, ~102% of one core, ~125–139 MB RSS — consistent with paced ~15 Hz using ~⅓ of that core under concurrent load.

### Verdict (measured on device)

**`likely_ok_on_pi5_cpu` — confirmed on Pi, not just estimated.**

- Concurrent process CPU% sum ≈ **53% of one core** across four workers (~13% of total Pi capacity if cores were fully independent; real contention is softer with 4 cores).
- Combined RSS ≈ **429 MB** — fine on 8 GB.
- Face holds **~15 Hz** (p95 27 ms ≪ 66 ms frame budget).
- Phone holds **~5 Hz** (p95 29 ms); alert path &lt;1 s is not latency-bound.
- Still missing: CSI camera capture cost, BLE wearable, thermals / `vcgencmd get_throttled` under long soak, Hailo offload comparison.

### Implications

1. **AI HAT+ remains optional** for this three-model CPU schedule until camera+BLE soak says otherwise.
2. Keep phone at **5 Hz** and face around **15 Hz**.
3. Prefer Tailscale/LAN SSH for re-runs; tree lives at `~/RTDMS` on the Pi.

## Re-run on Pi

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
~/dms-face/.venv/bin/python ~/RTDMS/fusion/tools/sim_concurrent_pipeline.py \
  --seconds 60 --json ~/RTDMS/fusion/bench_sim_pi5.json
```
