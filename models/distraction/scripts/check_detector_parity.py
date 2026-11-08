#!/usr/bin/env python3
"""Check that the NCNN / ONNX runtimes (our own pre/post-processing) match Ultralytics.

    python scripts/check_detector_parity.py --images img1.jpg img2.jpg [--gray]

Every COCO class is kept (identity class map) so the comparison is not limited to the four
classes the rules use. Needs the training env (Ultralytics) for the reference.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rtdms_distraction.config import DetectorConfig  # noqa: E402
from rtdms_distraction.detector import load_class_names, make_detector  # noqa: E402
from rtdms_distraction.types import Box  # noqa: E402


def iou(a: Box, b: Box) -> float:
    from rtdms_distraction.types import intersection

    i = intersection(a, b)
    u = a.area + b.area - i
    return i / u if u > 0 else 0.0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--images", nargs="+", required=True)
    p.add_argument("--pt", default="models/yolo26n.pt")
    p.add_argument("--ncnn", default="models/yolo26n_coco_416_ncnn_model")
    p.add_argument("--onnx", default="models/yolo26n_coco_416.onnx")
    p.add_argument("--imgsz", type=int, default=416)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--gray", action="store_true", help="feed grayscale x3 like the pipeline")
    args = p.parse_args()

    names = load_class_names(Path(args.ncnn))
    def cfg(backend, weights):
        return DetectorConfig(backend=backend, weights=weights, imgsz=args.imgsz,
                              class_map={n: n for n in names}, conf={"_": args.conf})

    ref = make_detector(cfg("ultralytics", args.pt))
    others = {"ncnn": make_detector(cfg("ncnn", args.ncnn))}
    if Path(args.onnx).is_file():
        others["onnx"] = make_detector(cfg("onnx", args.onnx))

    worst = 0.0
    total_ref = matched = 0
    for path in args.images:
        bgr = cv2.imread(path)
        # Every backend takes OpenCV BGR (Ultralytics' numpy convention).
        img = cv2.cvtColor(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR) \
            if args.gray else bgr
        r = ref.detect(img)
        print(f"\n{Path(path).name}: ultralytics {len(r)} boxes")
        for name, det in others.items():
            o = det.detect(img)
            pairs = []
            for a in r:
                best = max(o, key=lambda b, a=a: iou(a.box, b.box) if a.cls == b.cls else -1,
                           default=None)
                if best is not None and best.cls == a.cls and iou(a.box, best.box) > 0.5:
                    pairs.append((a, best, iou(a.box, best.box)))
            dconf = max((abs(a.conf - b.conf) for a, b, _ in pairs), default=0.0)
            min_iou = min((x for _, _, x in pairs), default=1.0)
            worst = max(worst, dconf)
            total_ref += len(r)
            matched += len(pairs)
            print(f"  {name:5s}: {len(o)} boxes, matched {len(pairs)}/{len(r)}, "
                  f"min IoU {min_iou:.3f}, max |dconf| {dconf:.3f}")
            for a in r:
                print(f"     ref {a.cls:14s} {a.conf:.2f} {a.box.as_list()}")
    print(f"\nmatched {matched}/{total_ref} reference boxes; worst |dconf| {worst:.3f}")
    return 0 if matched == total_ref else 1


if __name__ == "__main__":
    raise SystemExit(main())
