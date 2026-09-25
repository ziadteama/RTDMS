#!/usr/bin/env python3
"""Still-image latency bench for the phone pipeline (no camera required)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--images", type=Path, help="Directory of images; synthetic if omitted")
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--json", type=Path)
    args = p.parse_args()

    from dms_phone.config import Config
    from dms_phone.pipeline import PhonePipeline

    pipe = PhonePipeline(Config())
    frames: list[np.ndarray] = []
    if args.images and args.images.is_dir():
        try:
            import cv2
        except ImportError as exc:
            raise SystemExit("opencv required for --images") from exc
        for path in sorted(args.images.glob("*"))[: args.n]:
            im = cv2.imread(str(path))
            if im is not None:
                frames.append(im)
    if not frames:
        frames = [np.zeros((240, 320, 3), dtype=np.uint8) for _ in range(args.n)]

    # Disable rate limit for pure latency by setting high hz
    pipe.cfg.detector.infer_hz = 1000.0
    latencies: list[float] = []
    for i, frame in enumerate(frames):
        t0 = time.perf_counter()
        pipe.process(frame, now=float(i))
        latencies.append((time.perf_counter() - t0) * 1000.0)

    summary = {
        "n": len(latencies),
        "mean_ms": sum(latencies) / len(latencies),
        "p95_ms": sorted(latencies)[int(0.95 * (len(latencies) - 1))],
        "backend": "stub_or_onnx",
    }
    print(json.dumps(summary, indent=2))
    if args.json:
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
