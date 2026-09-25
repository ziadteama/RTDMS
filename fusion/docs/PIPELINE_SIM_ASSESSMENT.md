# Concurrent pipeline simulation — Pi readiness (no hardware)

**Date:** 2026-09-25  
**Mode:** concurrent processes, no camera / no ESP / no wearable  
**Host:** Windows 11, Python 3.12, ~20 logical cores, 16.8 GB RAM (laptop — **not** the Pi)  
**Artifact:** [`bench_sim.json`](bench_sim.json)  
**Runner:** `py -3.12 fusion/tools/sim_concurrent_pipeline.py --seconds 25`

## What ran

| Process | Stimulus | Target rate |
|---|---|---|
| `dms-face` | Fixed `portrait.jpg` through MediaPipe FacePipeline | ~15 Hz paced |
| `dms-phone` | Random frames through ONNX `phone_cls.onnx` | ~5 Hz (rate-limited) |
| `dms-physiology` | Synthetic PPG replay, realtime paced | 100 Hz samples |
| `dms-fusion` | `decide()` stub | 10 Hz |

Thread caps: `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`.

## Measured (25 s wall)

| Model | Achieved Hz | Latency p95 (ms) | CPU % (proc) | RSS (MB) |
|---|---:|---:|---:|---:|
| Face | 14.9 | 10.4 | 13.5 | 114 |
| Phone | 4.7 | 7.9 | 3.9 | 84 |
| Physiology | — (25 outputs; still `WARMUP` at 25 s) | — | 0.6 | 102 |
| Fusion | 10 | 0.02 | 0.1 | 23 |
| **Sum** | | | **~18** | **~324** |

Physiology `WARMUP` is expected: the service needs ~60 s of valid PPG before `VALID` / HR. CPU/RSS still reflect live filtering under concurrent load.

## Assessment for Raspberry Pi 5

**Verdict (heuristic): `likely_ok_on_pi5_cpu`**

- Host concurrent CPU sum ≈ **18% of one logical core**. A crude ×2 scale for Pi ARM → ~**36% of one Pi core** equivalent for this workload shape — well under 4 cores, with headroom for capture + GPIO.
- Combined RSS ≈ **324 MB** — comfortable on 8 GB Pi (physiology alone was already measured ~108 MB on device).
- Face and phone latencies on the laptop leave margin for the report targets (face ~15 fps, phone alert &lt;1 s at 5 Hz).
- Does **not** replace a real Pi concurrent soak (`vcgencmd get_throttled`, CSI camera, BLE). Treat as **upper-bound optimism** for face/phone (laptop is faster) and a **shape check** that the scheduling (15 Hz + 5 Hz + physio) is sane.

### Implications

1. **AI HAT+ remains optional** for this three-model schedule until Pi re-measure says otherwise — matches the open question in `Subsystems/Pi Setup Plan.md`.
2. Keep phone at **5 Hz** and face around **15 Hz**; do not raise rates without a Pi bench.
3. Next gate: copy the same script to the Pi (or SSH-run) once packages are installed there — prefer LAN key auth.

## Re-run

```bash
py -3.12 -m pip install -e models/physiology -e "models/phone[runtime]" -e "models/face[bench]" -e fusion psutil
py -3.12 fusion/tools/sim_concurrent_pipeline.py --seconds 60 --json fusion/bench_sim.json
```
