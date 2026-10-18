#!/usr/bin/env python3
"""Per-class precision / recall / AP50 of detectors on a YOLO-format test set, OUR classes.

    python scripts/eval_detector.py --list D:/rtdms-data/datasets/v1/test.txt \
        --models models/yolo26n.pt D:/rtdms-data/runs/v1_416/weights/best.pt --imgsz 416

COCO models are mapped to our classes (cell phone -> phone, cup/bottle/wine glass -> drink, COCO
foods -> food; no hand). Fine-tuned models already use phone / drink / food / hand. Same
matching for every model: IoU >= 0.5, greedy by confidence, P/R reported at --conf.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np

CLASSES = ["phone", "drink", "food", "hand"]
COCO = {"cell phone": "phone", "cup": "drink", "bottle": "drink", "wine glass": "drink",
        "banana": "food", "apple": "food", "sandwich": "food", "orange": "food",
        "hot dog": "food", "pizza": "food", "donut": "food", "cake": "food"}


def label_path(im: str) -> str:
    a, b = f"{os.sep}images{os.sep}", f"{os.sep}labels{os.sep}"
    i = im.rfind(a)
    return str(Path(im[:i] + b + im[i + len(a):]).with_suffix(".txt")) if i >= 0 else ""


def read_gt(im: str, w: int, h: int) -> list[tuple[int, np.ndarray]]:
    p = Path(label_path(im))
    out = []
    if p.is_file():
        for line in p.read_text(encoding="utf8").split("\n"):
            if line.strip():
                c, cx, cy, bw, bh = (float(v) for v in line.split())
                out.append((int(c), np.array([(cx - bw / 2) * w, (cy - bh / 2) * h,
                                              (cx + bw / 2) * w, (cy + bh / 2) * h])))
    return out


def iou(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    i = w * h
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def ap(tp: np.ndarray, conf: np.ndarray, n_gt: int) -> float:
    if n_gt == 0:
        return float("nan")
    if len(tp) == 0:
        return 0.0
    o = np.argsort(-conf)
    tp = tp[o]
    ctp = np.cumsum(tp)
    rec = ctp / n_gt
    prec = ctp / np.arange(1, len(tp) + 1)
    mrec = np.concatenate([[0], rec, [1]])
    mpre = np.concatenate([[1], prec, [0]])
    mpre = np.flip(np.maximum.accumulate(np.flip(mpre)))
    x = np.linspace(0, 1, 101)
    return float(np.trapezoid(np.interp(x, mrec, mpre), x))


def evaluate(model, images: list[str], imgsz: int, conf: float, gray: bool) -> dict:
    import cv2

    names = model.names
    cmap = {i: (COCO.get(n) if n in COCO else (n if n in CLASSES else None))
            for i, n in names.items()}
    has = {c for c in cmap.values() if c}
    rec = {c: {"tp": [], "conf": [], "n_gt": 0} for c in CLASSES}
    for im in images:
        img = cv2.imread(im)
        if img is None:
            continue
        if gray:
            img = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        h, w = img.shape[:2]
        gts = read_gt(im, w, h)
        r = model.predict(img, imgsz=imgsz, conf=0.01, rect=False, verbose=False)[0].boxes
        preds = [(cmap[int(k)], float(c), xy) for xy, c, k in
                 zip(r.xyxy.cpu().numpy(), r.conf.cpu().numpy(), r.cls.cpu().numpy(),
                     strict=True) if cmap.get(int(k))]
        for c in CLASSES:
            g = [b for k, b in gts if CLASSES[k] == c]
            rec[c]["n_gt"] += len(g)
            used = [False] * len(g)
            for _, cf, xy in sorted((p for p in preds if p[0] == c), key=lambda p: -p[1]):
                best, bi = 0.0, -1
                for j, gb in enumerate(g):
                    if not used[j]:
                        v = iou(xy, gb)
                        if v > best:
                            best, bi = v, j
                hit = best >= 0.5
                if hit:
                    used[bi] = True
                rec[c]["tp"].append(1.0 if hit else 0.0)
                rec[c]["conf"].append(cf)
    out = {}
    for c in CLASSES:
        tp, cf, n = np.array(rec[c]["tp"]), np.array(rec[c]["conf"]), rec[c]["n_gt"]
        if c not in has:
            out[c] = {"n_gt": n, "P": None, "R": None, "AP50": None, "note": "class not in model"}
            continue
        sel = cf >= conf
        tps = float(tp[sel].sum()) if len(tp) else 0.0
        out[c] = {"n_gt": n, "P": round(tps / max(1, int(sel.sum())), 3),
                  "R": round(tps / max(1, n), 3), "AP50": round(ap(tp, cf, n), 3)}
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--list", required=True, help="txt file of image paths (YOLO layout)")
    p.add_argument("--models", nargs="+", required=True)
    p.add_argument("--imgsz", type=int, nargs="+", default=[416])
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--gray", action="store_true", help="force gray input (for colour sets)")
    p.add_argument("--limit", type=int)
    p.add_argument("--json")
    args = p.parse_args()

    from ultralytics import YOLO

    images = [ln.strip() for ln in Path(args.list).read_text(encoding="utf8").split("\n")
              if ln.strip()][: args.limit]
    results = {}
    for m in args.models:
        model = YOLO(m)
        for sz in args.imgsz:
            key = f"{Path(m).parent.parent.name if 'weights' in m else Path(m).stem}@{sz}"
            results[key] = evaluate(model, images, sz, args.conf, args.gray)
            print(f"\n{key}  ({len(images)} images, P/R at conf {args.conf}, IoU 0.5)")
            for c, r in results[key].items():
                if r["P"] is None:
                    print(f"  {c:6s} n_gt {r['n_gt']:5d}   -- not a class of this model")
                else:
                    print(f"  {c:6s} n_gt {r['n_gt']:5d}   P {r['P']:.3f}  R {r['R']:.3f}  "
                          f"AP50 {r['AP50']:.3f}")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
