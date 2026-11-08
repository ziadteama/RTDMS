#!/usr/bin/env python3
"""Per-stage benchmark: capture, rectify, detect, face mesh, hands, rules + temperature/throttling.

    python scripts/bench.py --duration 60                         # Pi camera, live
    python scripts/bench.py --video data/drive.mp4 --duration 60  # repeatable input
    python scripts/bench.py --duration 1800 --json bench_pi_30min.json   # Phase 4 soak

Numbers from this script are STANDALONE (this process only). The repo gates resource budgets on
CONCURRENT runs with face + physiology live; label results accordingly.

On a live camera, `capture_wait` is the time spent waiting for the next frame (bounded by the
sensor frame rate, not a cost) and `capture_grab` is the time inside the camera read itself.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))

from run import apply_overrides  # noqa: E402

from rtdms_distraction.capture import open_source  # noqa: E402
from rtdms_distraction.config import load_pipeline_config, load_rules_config  # noqa: E402
from rtdms_distraction.pipeline import DistractionPipeline  # noqa: E402

STAGES = ("capture_wait", "capture_grab", "rectify", "detect", "facemesh", "hands", "rules")


def cpu_temp() -> float | None:
    try:
        return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000.0
    except (OSError, ValueError):
        return None


def throttled() -> str | None:
    if not shutil.which("vcgencmd"):
        return None
    try:
        out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True,
                             timeout=2).stdout.strip()
        return out.split("=")[-1]
    except (OSError, subprocess.SubprocessError):
        return None


def stats(v: list[float]) -> dict[str, float]:
    if not v:
        return {"n": 0}
    a = np.array(v)
    return {"n": len(a), "mean": round(float(a.mean()), 2), "p50": round(float(np.median(a)), 2),
            "p95": round(float(np.percentile(a, 95)), 2), "max": round(float(a.max()), 2)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--config", help="pipeline.yaml (default configs/pipeline.yaml)")
    p.add_argument("--video")
    p.add_argument("--camera-index", type=int)
    p.add_argument("--duration", type=float, default=60.0, help="wall-clock seconds")
    p.add_argument("--warmup", type=int, default=30, help="frames excluded from stats")
    p.add_argument("--no-rectify", action="store_true")
    p.add_argument("--roi")
    p.add_argument("--driver-side", choices=["right", "left"])
    p.add_argument("--detector-backend", choices=["ncnn", "onnx", "ultralytics"])
    p.add_argument("--weights")
    p.add_argument("--detect-every", type=int)
    p.add_argument("--hands", choices=["mediapipe", "detector", "off"])
    p.add_argument("--loop", action="store_true", help="restart the video at its end")
    p.add_argument("--json", help="write results here")
    args = p.parse_args()
    args.per_frame_log = False
    args.log_dir = None

    pcfg = load_pipeline_config(args.config)
    rcfg = load_rules_config()
    apply_overrides(pcfg, args)
    c = pcfg.capture

    def open_src():
        return open_source(c.width, c.height, c.fps, video=args.video,
                           camera_index=args.camera_index).start()

    src = open_src()
    pipe = DistractionPipeline(pcfg, rcfg, src.size)
    samples: dict[str, list[float]] = {k: [] for k in STAGES}
    total_ms: list[float] = []
    thermal = [{"t": 0.0, "temp_c": cpu_temp(), "throttled": throttled()}]
    detector_runs = frames = 0
    t_start = time.perf_counter()
    t_measure = None
    next_thermal = 5.0
    psutil = None
    try:
        import psutil as _ps
        psutil = _ps
        proc = psutil.Process()
        proc.cpu_percent(None)
    except ImportError:
        pass

    while True:
        elapsed = time.perf_counter() - t_start
        if elapsed >= args.duration:
            break
        t0 = time.perf_counter()
        gray, ts = src.read()
        wait = (time.perf_counter() - t0) * 1000
        if gray is None:
            if args.loop and args.video:
                src.stop()
                src = open_src()
                continue
            break
        res = pipe.process(gray, ts)
        frames += 1
        if frames == args.warmup:
            t_measure = time.perf_counter()
        if frames > args.warmup:
            samples["capture_wait"].append(wait)
            samples["capture_grab"].append(getattr(src, "grab_ms", wait))
            for k, v in res.timings_ms.items():
                if k == "detect" and not res.detector_ran:
                    continue
                samples[k].append(v)
            detector_runs += res.detector_ran
            total_ms.append(sum(res.timings_ms.values()))
        if elapsed >= next_thermal:
            next_thermal += 5.0
            thermal.append({"t": round(elapsed, 1), "temp_c": cpu_temp(),
                            "throttled": throttled()})

    wall = time.perf_counter() - (t_measure or t_start)
    measured = max(0, frames - args.warmup)
    thermal.append({"t": round(time.perf_counter() - t_start, 1), "temp_c": cpu_temp(),
                    "throttled": throttled()})
    src.stop()
    pipe.close()

    result = {
        "host": platform.node(), "machine": platform.machine(), "python": platform.python_version(),
        "pi": Path("/proc/device-tree/model").is_file(), "cpus": os.cpu_count(),
        "source": args.video or "camera", "frames_measured": measured,
        "wall_s": round(wall, 2), "fps_end_to_end": round(measured / wall, 2) if wall else None,
        "pipeline_only_fps": round(1000 / np.mean(total_ms), 2) if total_ms else None,
        "detector_every_n": pcfg.detector.every_n, "detector_runs": detector_runs,
        "config": {"detector": pcfg.detector.backend, "weights": pcfg.detector.weights,
                   "imgsz": pcfg.detector.imgsz, "threads": pcfg.detector.num_threads,
                   "facemesh": pcfg.facemesh.backend, "hands": pcfg.hands.source,
                   "hands_every_n": pcfg.hands.every_n, "rectify": pcfg.rectify.enabled,
                   "view": [pipe.roi.out_w, pipe.roi.out_h]},
        "stages_ms": {k: stats(v) for k, v in samples.items()},
        "pipeline_ms": stats(total_ms),
        "process_cpu_percent": round(proc.cpu_percent(None), 1) if psutil else None,
        "thermal": thermal,
        "scope": "standalone (not concurrent with face/physiology)",
    }

    print(f"\n{'stage':14s} {'mean':>7s} {'p50':>7s} {'p95':>7s} {'max':>7s}  (ms)")
    for k, s in list(result["stages_ms"].items()) + [("PIPELINE", result["pipeline_ms"])]:
        if s.get("n"):
            print(f"{k:14s} {s['mean']:7.2f} {s['p50']:7.2f} {s['p95']:7.2f} {s['max']:7.2f}")
    print(f"\nend-to-end {result['fps_end_to_end']} FPS over {measured} frames "
          f"(pipeline-only {result['pipeline_only_fps']} FPS); detector ran {detector_runs}x")
    temps = [x["temp_c"] for x in thermal if x["temp_c"] is not None]
    if temps:
        print(f"CPU temp {temps[0]:.1f} -> {temps[-1]:.1f} C (max {max(temps):.1f})")
    th = {x["throttled"] for x in thermal if x["throttled"] is not None}
    if th:
        print(f"throttled flags seen: {sorted(th)}" + ("" if th == {"0x0"} else
              "  <-- NON-ZERO: timings from this run are not valid budget evidence"))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2), encoding="utf8")
        print(f"-> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
