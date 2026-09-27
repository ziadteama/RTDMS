#!/usr/bin/env python3
"""No-hardware concurrent pipeline simulation for Pi readiness assessment.

Runs face (still image), phone (ONNX @ 5 Hz), physiology (synthetic PPG replay),
and fusion decide() concurrently, sampling CPU%% / RSS.

    py -3.12 fusion/tools/sim_concurrent_pipeline.py --seconds 30 --json fusion/bench_sim.json

Requires editable installs of dms-face, dms-phone, dms-physiology, dms-fusion, psutil.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import statistics
import sys
import time
from pathlib import Path

# Thread discipline before numpy/ort/mediapipe import in workers
for _k in (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_k, "1")

REPO = Path(__file__).resolve().parents[2]
FACE_ROOT = REPO / "models" / "face"
PHONE_ROOT = REPO / "models" / "phone"
PORTRAIT = FACE_ROOT / "tests" / "assets" / "portrait.jpg"


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, int(p * (len(s) - 1))))]


def worker_face(seconds: float, width: int, height: int, q: mp.Queue) -> None:
    os.chdir(FACE_ROOT)
    import cv2
    import numpy as np
    import psutil
    from dms_face.calibration import DriverProfile
    from dms_face.config import Config
    from dms_face.pipeline import FacePipeline

    bgr = cv2.imread(str(PORTRAIT))
    if bgr is None:
        q.put({"name": "face", "error": f"missing {PORTRAIT}"})
        return
    bgr = cv2.resize(bgr, (width, height))
    rgb = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))

    cfg = Config()
    cfg.camera.width, cfg.camera.height = width, height
    pipe = FacePipeline(cfg, DriverProfile(), width=width, height=height)
    proc = psutil.Process()
    proc.cpu_percent(None)

    lat: list[float] = []
    outs = 0
    t0 = time.perf_counter()
    ts = 0.0
    # warmup
    for _ in range(5):
        pipe.process(rgb, ts)
        ts += 1.0 / 15.0

    cpu_samples: list[float] = []
    while time.perf_counter() - t0 < seconds:
        a = time.perf_counter()
        res = pipe.process(rgb, ts)
        lat.append((time.perf_counter() - a) * 1000.0)
        outs += 1
        ts += 1.0 / 15.0  # target ~15 fps workload
        # pace to ~15 Hz so CPU reflects sustained rate, not burst
        sleep_for = (1.0 / 15.0) - (time.perf_counter() - a)
        if sleep_for > 0:
            time.sleep(sleep_for)
        if outs % 15 == 0:
            cpu_samples.append(proc.cpu_percent(None))

    wall = time.perf_counter() - t0
    pipe.close()
    q.put(
        {
            "name": "face",
            "frames": outs,
            "wall_s": round(wall, 2),
            "target_hz": 15.0,
            "achieved_hz": round(outs / wall, 2) if wall else 0.0,
            "latency_ms_mean": round(statistics.mean(lat), 2) if lat else None,
            "latency_ms_p95": round(_pct(lat, 0.95), 2) if lat else None,
            "cpu_percent_mean": round(statistics.mean(cpu_samples), 1) if cpu_samples else None,
            "rss_mb": round(proc.memory_info().rss / 1e6, 1),
            "last_state": getattr(getattr(res, "report", None), "state", None)
            and res.report.state.value,
        }
    )


def worker_phone(seconds: float, q: mp.Queue) -> None:
    os.chdir(PHONE_ROOT)
    import numpy as np
    import psutil
    from dms_phone.config import Config
    from dms_phone.pipeline import PhonePipeline

    cfg = Config()
    pipe = PhonePipeline(cfg)
    # Keep configured 5 Hz rate limit
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    proc = psutil.Process()
    proc.cpu_percent(None)

    lat: list[float] = []
    outs = 0
    skipped = 0
    t0 = time.perf_counter()
    now = 0.0
    cpu_samples: list[float] = []
    last_top = None

    while time.perf_counter() - t0 < seconds:
        a = time.perf_counter()
        out = pipe.process(frame, now=now)
        dt = (time.perf_counter() - a) * 1000.0
        if out is None:
            skipped += 1
        else:
            lat.append(dt)
            outs += 1
            last_top = out.top_class.value if out.top_class else None
        now += 0.05  # poll at 20 Hz; pipeline rate-limits to 5 Hz
        sleep_for = 0.05 - (time.perf_counter() - a)
        if sleep_for > 0:
            time.sleep(sleep_for)
        if (outs + skipped) % 20 == 0:
            cpu_samples.append(proc.cpu_percent(None))

    wall = time.perf_counter() - t0
    q.put(
        {
            "name": "phone",
            "publishes": outs,
            "skipped_rate_limit": skipped,
            "wall_s": round(wall, 2),
            "target_hz": 5.0,
            "achieved_hz": round(outs / wall, 2) if wall else 0.0,
            "latency_ms_mean": round(statistics.mean(lat), 2) if lat else None,
            "latency_ms_p95": round(_pct(lat, 0.95), 2) if lat else None,
            "cpu_percent_mean": round(statistics.mean(cpu_samples), 1) if cpu_samples else None,
            "rss_mb": round(proc.memory_info().rss / 1e6, 1),
            "last_top_class": last_top,
            "backend": getattr(pipe.detector, "_model_path", "stub/onnx"),
        }
    )


def worker_physio(seconds: float, q: mp.Queue) -> None:
    import asyncio

    import psutil
    from dms_physiology.acquisition import ReplaySource
    from dms_physiology.fusion import InMemorySink
    from dms_physiology.service import PhysiologyService
    from dms_physiology.simulate import synthetic_frames

    # Use realtime pacing for wall-clock load, but cap seconds of *signal*
    # to the run duration so the worker ends with the others.
    signal_s = max(5, int(seconds) + 2)
    frames = synthetic_frames(signal_s)
    sink = InMemorySink()
    # realtime=True paces to sample clock (~wall time)
    src = ReplaySource(frames, realtime=True)
    proc = psutil.Process()
    proc.cpu_percent(None)

    async def _run() -> None:
        svc = PhysiologyService(src, sink)
        task = asyncio.create_task(svc.run())
        t0 = time.perf_counter()
        cpu_samples: list[float] = []
        while time.perf_counter() - t0 < seconds:
            await asyncio.sleep(0.5)
            cpu_samples.append(proc.cpu_percent(None))
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return cpu_samples

    t0 = time.perf_counter()
    cpu_samples = asyncio.run(_run())
    wall = time.perf_counter() - t0
    last = sink.outputs[-1] if sink.outputs else {}
    q.put(
        {
            "name": "physiology",
            "outputs": len(sink.outputs),
            "wall_s": round(wall, 2),
            "cpu_percent_mean": round(statistics.mean(cpu_samples), 1) if cpu_samples else None,
            "rss_mb": round(proc.memory_info().rss / 1e6, 1),
            "last_state": last.get("state"),
            "last_hr": last.get("hr_bpm") or last.get("hr"),
        }
    )


def worker_fusion_idle(seconds: float, q: mp.Queue) -> None:
    """Cheap fusion loop — mirrors decide() cost under concurrent load."""
    import psutil
    from dms_fusion import decide

    proc = psutil.Process()
    proc.cpu_percent(None)
    lat: list[float] = []
    n = 0
    t0 = time.perf_counter()
    cpu_samples: list[float] = []
    face = {"state": "alert"}
    phone = {"phone_score": 0.1, "sustained_phone_ms": 0.0}
    phys = {"fatigue_probability": 0.2}
    while time.perf_counter() - t0 < seconds:
        a = time.perf_counter()
        decide(face=face, phone=phone, physiology=phys)
        lat.append((time.perf_counter() - a) * 1000.0)
        n += 1
        time.sleep(0.1)  # 10 Hz fusion tick
        if n % 10 == 0:
            cpu_samples.append(proc.cpu_percent(None))
    wall = time.perf_counter() - t0
    q.put(
        {
            "name": "fusion",
            "ticks": n,
            "wall_s": round(wall, 2),
            "latency_ms_mean": round(statistics.mean(lat), 4) if lat else None,
            "cpu_percent_mean": round(statistics.mean(cpu_samples), 1) if cpu_samples else None,
            "rss_mb": round(proc.memory_info().rss / 1e6, 1),
        }
    )


def _on_pi(report: dict) -> bool:
    plat = ((report.get("host") or {}).get("platform") or "").lower()
    return "aarch64" in plat and ("rpi" in plat or "raspberry" in plat)


def assess(report: dict) -> dict:
    """Pi readiness from concurrent numbers. On non-Pi hosts, applies a heuristic scale."""
    by = {m["name"]: m for m in report["models"] if "error" not in m}
    face_cpu = (by.get("face") or {}).get("cpu_percent_mean") or 0.0
    phone_cpu = (by.get("phone") or {}).get("cpu_percent_mean") or 0.0
    phys_cpu = (by.get("physiology") or {}).get("cpu_percent_mean") or 0.0
    fusion_cpu = (by.get("fusion") or {}).get("cpu_percent_mean") or 0.0
    # Process.cpu_percent is relative to one logical core
    sum_cpu = face_cpu + phone_cpu + phys_cpu + fusion_cpu
    rss = sum((by.get(k) or {}).get("rss_mb") or 0.0 for k in ("face", "phone", "physiology", "fusion"))

    face_lat = (by.get("face") or {}).get("latency_ms_p95") or 0.0
    phone_lat = (by.get("phone") or {}).get("latency_ms_p95") or 0.0

    on_pi = _on_pi(report)
    notes: list[str] = []
    # Rough scale only when extrapolating from a faster laptop host
    pi_cpu_scale = 1.0 if on_pi else 2.0
    est_pi_sum = sum_cpu * pi_cpu_scale
    where = "Pi" if on_pi else "host"
    notes.append(
        f"{where.capitalize()} concurrent process CPU% sum ≈ {sum_cpu:.0f}% of one logical core "
        f"(face {face_cpu}, phone {phone_cpu}, physio {phys_cpu}, fusion {fusion_cpu})."
    )
    if on_pi:
        notes.append("Measured on Raspberry Pi — no laptop→Pi scale applied.")
    else:
        notes.append(
            f"Naive Pi estimate ×{pi_cpu_scale}: ~{est_pi_sum:.0f}% of one Pi core equivalent "
            "(very rough — re-measure on device)."
        )
    notes.append(f"Combined RSS ≈ {rss:.0f} MB.")
    if face_lat and face_lat > 66:
        notes.append(f"Face p95 {face_lat} ms > 66 ms → may miss 15 fps target under load.")
    else:
        notes.append(f"Face p95 {face_lat} ms looks compatible with ~15 fps.")
    if phone_lat and phone_lat > 200:
        notes.append(f"Phone p95 {phone_lat} ms high for 5 Hz; check ORT threads.")
    else:
        notes.append(f"Phone p95 {phone_lat} ms OK for 5 Hz / <1 s alert.")

    verdict = "likely_ok_on_pi5_cpu"
    if est_pi_sum > 350 or rss > 2500:
        verdict = "tight_or_risky_without_hat"
    if face_lat > 100 or phone_lat > 400:
        verdict = "needs_remeasure_latency_high"

    return {
        "measured_on_pi": on_pi,
        "host_cpu_percent_sum": round(sum_cpu, 1),
        "est_pi_cpu_percent_sum": round(est_pi_sum, 1),
        "rss_mb_sum": round(rss, 1),
        "verdict": verdict,
        "notes": notes,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seconds", type=float, default=30.0)
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--json", type=Path, default=REPO / "fusion" / "bench_sim.json")
    p.add_argument("--skip-face", action="store_true")
    p.add_argument("--skip-phone", action="store_true")
    p.add_argument("--skip-physio", action="store_true")
    args = p.parse_args()

    import platform

    import psutil

    q: mp.Queue = mp.Queue()
    procs: list[mp.Process] = []
    specs = [
        ("face", not args.skip_face, worker_face, (args.seconds, args.width, args.height, q)),
        ("phone", not args.skip_phone, worker_phone, (args.seconds, q)),
        ("physiology", not args.skip_physio, worker_physio, (args.seconds, q)),
        ("fusion", True, worker_fusion_idle, (args.seconds, q)),
    ]

    t0 = time.perf_counter()
    for name, enabled, fn, fn_args in specs:
        if not enabled:
            continue
        pr = mp.Process(target=fn, args=fn_args, name=name)
        pr.start()
        procs.append(pr)

    results = []
    for _ in procs:
        results.append(q.get(timeout=args.seconds + 120))

    for pr in procs:
        pr.join(timeout=30)
        if pr.is_alive():
            pr.terminate()

    wall = time.perf_counter() - t0
    plat = platform.platform()
    on_pi = "aarch64" in plat.lower() and (
        "rpi" in plat.lower() or "raspberry" in plat.lower()
    )
    report = {
        "schema_version": 1,
        "mode": "concurrent_no_hardware",
        "wall_s": round(wall, 2),
        "host": {
            "platform": plat,
            "python": platform.python_version(),
            "logical_cores": psutil.cpu_count(logical=True),
            "ram_gb": round(psutil.virtual_memory().total / 1e9, 1),
            "note": (
                "Measured on Raspberry Pi 5 — authoritative concurrent numbers."
                if on_pi
                else "Laptop/host numbers — not Pi. Scale factor in assessment is heuristic only."
            ),
        },
        "models": results,
        "thread_env": {k: os.environ.get(k) for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS")},
    }
    report["assessment"] = assess(report)

    text = json.dumps(report, indent=2)
    print(text)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(text, encoding="utf-8")
    print(f"\nWrote {args.json}", file=sys.stderr)


if __name__ == "__main__":
    mp.freeze_support()
    main()
