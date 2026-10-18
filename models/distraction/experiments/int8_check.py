"""Frame-level check of NCNN detectors (e.g. FP32 vs INT8) on SynDD validation frames with labels:
phone / drink precision and recall at IoU 0.5 and the deployed thresholds, plus ms per frame.
python experiments/int8_check.py <ncnn dir> [<ncnn dir> ...] [--n 600]"""
import argparse
import copy
import glob
import random
import time
from pathlib import Path

import cv2
import numpy as np
from _paths import DATA, REPO

from rtdms_distraction.config import load_pipeline_config
from rtdms_distraction.detector import make_detector

NAMES = {0: "phone", 1: "drink", 2: "food"}


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("models", nargs="+")
    p.add_argument("--n", type=int, default=600)
    a = p.parse_args()
    imgs = sorted(glob.glob(f"{DATA}/det_v2/syndd/images/val/*.jpg"))
    random.Random(0).shuffle(imgs)
    imgs = imgs[: a.n]
    base = load_pipeline_config()
    for m in a.models:
        cfg = copy.deepcopy(base.detector)
        cfg.weights, cfg.imgsz, cfg.backend = str(Path(m).resolve()), 512, "ncnn"
        det = make_detector(cfg)
        tp = {c: 0 for c in ("phone", "drink")}
        fp, fn = dict(tp), dict(tp)
        ms = []
        for f in imgs:
            g = cv2.cvtColor(cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
            h, w = g.shape[:2]
            t0 = time.perf_counter()
            dets = det.detect(g)
            ms.append((time.perf_counter() - t0) * 1000)
            lab = Path(f.replace("images", "labels")).with_suffix(".txt")
            gt = []
            for ln in lab.read_text().splitlines():
                c, x, y, bw, bh = map(float, ln.split())
                gt.append((NAMES[int(c)], ((x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w,
                                           (y + bh / 2) * h)))
            for c in tp:
                g_ = [b for k, b in gt if k == c]
                p_ = [(d.box.x1, d.box.y1, d.box.x2, d.box.y2) for d in dets if d.cls == c]
                used = set()
                for pb in p_:
                    j = max(range(len(g_)), key=lambda i: iou(pb, g_[i]), default=None)
                    if j is not None and j not in used and iou(pb, g_[j]) >= 0.5:
                        tp[c] += 1
                        used.add(j)
                    else:
                        fp[c] += 1
                fn[c] += len(g_) - len(used)
        res = {c: f"P {tp[c] / max(1, tp[c] + fp[c]):.3f} R {tp[c] / max(1, tp[c] + fn[c]):.3f}"
               for c in tp}
        print(f"{Path(m).name:45s} {res}  {np.median(ms[10:]):.1f} ms/frame", flush=True)


if __name__ == "__main__":
    REPO  # noqa: B018  (import keeps src/ on sys.path)
    main()
