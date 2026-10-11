#!/usr/bin/env python3
"""End-to-end speed of the live.py pipeline on a recorded laptop-webcam clip, per ear setup.

    python scripts/bench_live.py data/recordings/S01_guided_day_20261010T152706Z.mp4

Same profile, detector choice and overlay as live.py; frames come from the file instead of the
camera (capture itself is not timed; the webcam delivers <= 30 fps). Each setup builds the
pipeline with only its models loaded, so the cost is what that setup alone would pay:
  hands            pose off, crop classifiers off
  hands+pose       pose on (every pose.every_n frames)
  hands+pose+clf   pose + ear and mouth crop classifiers (= live.py with everything loaded)
Prints fps and mean per-stage ms. Nothing is written.
"""

from __future__ import annotations

import argparse
import copy
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from live import build_detector, discover_models  # noqa: E402

from rtdms_distraction.config import load_pipeline_config, load_rules_config  # noqa: E402
from rtdms_distraction.pipeline import DistractionPipeline  # noqa: E402
from rtdms_distraction.viz import render  # noqa: E402

SETUPS = {"hands": (False, False), "hands+pose": (True, False), "hands+pose+clf": (True, True)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("video")
    p.add_argument("--profile", default="laptop_webcam")
    p.add_argument("--frames", type=int, default=600)
    p.add_argument("--warmup", type=int, default=30)
    args = p.parse_args()

    cap = cv2.VideoCapture(args.video)
    frames = []
    while len(frames) < args.frames + args.warmup:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    if not frames:
        raise SystemExit(f"no frames in {args.video}")
    base, rcfg = load_pipeline_config(profile=args.profile), load_rules_config()
    h, w = frames[0].shape[:2]
    print(f"{args.video}: {len(frames)} frames {w}x{h}")
    for name, (pose, clf) in SETUPS.items():
        pcfg = copy.deepcopy(base)
        pcfg.pose.enabled = pose
        pcfg.ear_classifier.enabled = pcfg.mouth_classifier.enabled = clf
        m = (discover_models(pcfg.live.models) or [None])[0]
        conf = min(pcfg.detector.conf.values()) if pcfg.detector.conf else 0.25
        det = None
        if m is not None:
            pcfg.hands.source = m.hands
            det = build_detector(pcfg.detector, m, conf)
        pipe = DistractionPipeline(pcfg, rcfg, (w, h), detector=det)
        stages: dict[str, list[float]] = {}
        t_start, n = None, 0
        for i, f in enumerate(frames):
            if i == args.warmup:
                t_start = time.perf_counter()
            res = pipe.process(f, i / 30.0)
            render(res, 0.0, rcfg.phone_in_hand.holder_zones, debug=True, info=[],
                   classifier=None, banner=None)
            if t_start is not None:
                n += 1
                for k, v in res.timings_ms.items():
                    stages.setdefault(k, []).append(v)
        el = time.perf_counter() - t_start
        st = "  ".join(f"{k} {np.mean(v):.1f}" for k, v in stages.items())
        print(f"{name:15s} {n / el:5.1f} fps  ({1000 * el / n:.1f} ms/frame; "
              f"model {m.name if m else 'config'}; variant {pipe.variant})\n    ms: {st}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
