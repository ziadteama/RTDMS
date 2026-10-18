"""Simple-mode speed with the texting rule on / off (pose every pose.every_n frames).
python bench_simple.py <video> [frames] [start_s]"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import copy
import sys
import time

import cv2
import numpy as np

from live import build_detector, discover_models  # noqa: E402
from rtdms_distraction.config import load_pipeline_config, load_rules_config  # noqa: E402
from rtdms_distraction.pipeline import DistractionPipeline  # noqa: E402
from rtdms_distraction.viz import render  # noqa: E402


def main():
    video, nf = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 600
    start = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    frames = []
    while len(frames) < nf:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(cv2.resize(f, (1280, 720)))
    base = load_pipeline_config(profile="laptop_webcam")
    for texting in (False, True):
        pcfg, rcfg = copy.deepcopy(base), load_rules_config()
        rcfg.mode = "simple"
        rcfg.simple.texting = texting
        m = discover_models(pcfg.live.models)[0]
        det = build_detector(pcfg.detector, m, None)
        h, w = frames[0].shape[:2]
        pipe = DistractionPipeline(pcfg, rcfg, (w, h), detector=det)
        stages, levels = {}, {}
        t0 = None
        for i, f in enumerate(frames):
            if i == 30:
                t0 = time.perf_counter()
            res = pipe.process(f, i / 30.0)
            render(res, 0.0, rcfg.phone_in_hand.holder_zones, debug=True, info=[], classifier=None,
                   banner=None)
            for b, st in res.behaviours.items():
                levels.setdefault(b, {}).setdefault(st["level"], 0)
                levels[b][st["level"]] += 1
            if t0 is not None:
                for k, v in res.timings_ms.items():
                    stages.setdefault(k, []).append(v)
        el = time.perf_counter() - t0
        n = len(frames) - 30
        print(f"texting {texting}: {n / el:.1f} fps ({m.name}); baseline ready {res.baseline['ready']}; "
              f"ms " + " ".join(f"{k} {np.mean(v):.1f}" for k, v in stages.items()), flush=True)
        print("   levels", levels, flush=True)


if __name__ == "__main__":
    main()
