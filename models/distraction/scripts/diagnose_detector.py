#!/usr/bin/env python3
"""Which detector setting actually sees the phone / cup / food in a guided recording?

    python scripts/diagnose_detector.py data/recordings/S01_guided_day_<utc>.mp4

Uses the clip's .json timeline (from record.py --guided). For every segment it reports the share
of frames with at least one box of the expected class, per configuration:
model size (n/s/m) x imgsz (416/640) x colour vs grayscale x confidence threshold.
Runs Ultralytics .pt on the GPU with the square letterbox (identical to the NCNN export).
TRAINING ENV ONLY.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

EXPECT = {"phone_in_hand": "phone", "phone_right_ear": "phone", "phone_left_ear": "phone",
          "drinking": "drink", "eating": "food"}
CLASS_MAP = {"cell phone": "phone", "cup": "drink", "bottle": "drink", "wine glass": "drink",
             "banana": "food", "apple": "food", "sandwich": "food", "orange": "food",
             "hot dog": "food", "pizza": "food", "donut": "food", "cake": "food",
             # fine-tuned models use our names directly
             "phone": "phone", "drink": "drink", "food": "food", "hand": "hand"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("--models", default="yolo26n,yolo26s,yolo26m",
                   help="comma list: stock names (models/<name>.pt) or paths to .pt files")
    p.add_argument("--imgsz", default="416,640")
    p.add_argument("--confs", default="0.25,0.10")
    p.add_argument("--every", type=int, default=2, help="analyse every Nth frame")
    p.add_argument("--json", help="write results here")
    args = p.parse_args()

    from ultralytics import YOLO

    video = Path(args.video)
    meta = json.loads(video.with_suffix(".json").read_text(encoding="utf8"))
    fps = meta.get("measured_fps") or 30.0
    timeline = meta["timeline"]
    frames, times = [], []
    cap = cv2.VideoCapture(str(video))
    i = 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % args.every == 0:
            frames.append(f)
            times.append(i / fps)
        i += 1
    print(f"{video.name}: {i} frames @ {fps} fps, analysing {len(frames)}")

    def label_at(t):
        for seg in timeline:
            if seg["start"] <= t < seg["end"]:
                return seg["label"]
        return None

    labels = [label_at(t) for t in times]
    segs = [s for s in dict.fromkeys(labels) if s in EXPECT]
    min_conf = min(float(c) for c in args.confs.split(","))
    results = []
    for mname in args.models.split(","):
        # A bare name is a stock model in models/ (COCO classes); a path is e.g. a fine-tuned
        # best.pt whose classes are already phone / drink / food / hand.
        stock = Path(__file__).resolve().parents[1] / "models" / f"{mname}.pt"
        mpath = Path(mname) if Path(mname).suffix else stock
        model = YOLO(str(mpath))
        label = mpath.parent.parent.name if mpath.parent.name == "weights" else mpath.stem
        names = model.names
        for imgsz in (int(s) for s in args.imgsz.split(",")):
            for mode in ("color", "gray"):
                per_frame = []  # best conf per behaviour class in each frame
                for f in frames:
                    img = f if mode == "color" else cv2.cvtColor(
                        cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                    b = model.predict(img, imgsz=imgsz, conf=min_conf, rect=False,
                                      verbose=False)[0].boxes
                    best: dict[str, float] = {}
                    for c, k in zip(b.conf.cpu().numpy(), b.cls.cpu().numpy(), strict=True):
                        cls = CLASS_MAP.get(names[int(k)])
                        if cls:
                            best[cls] = max(best.get(cls, 0.0), float(c))
                    per_frame.append(best)
                for conf in (float(c) for c in args.confs.split(",")):
                    row = {"model": label, "imgsz": imgsz, "mode": mode, "conf": conf}
                    for s in segs:
                        idx = [j for j, lab in enumerate(labels) if lab == s]
                        hit = [per_frame[j].get(EXPECT[s], 0.0) >= conf for j in idx]
                        row[s] = round(float(np.mean(hit)), 2) if idx else None
                    # false positives: expected-class boxes during 'normal' / 'talking'
                    neg = [j for j, lab in enumerate(labels) if lab in ("normal", "talking")]
                    row["fp_phone_in_neg"] = round(float(np.mean(
                        [per_frame[j].get("phone", 0) >= conf for j in neg])), 2) if neg else None
                    results.append(row)
        print(f"  done {label}")

    cols = segs + ["fp_phone_in_neg"]
    head = f"{'model':12s} {'imgsz':>5s} {'mode':5s} {'conf':>4s} " + " ".join(
        f"{c[:13]:>13s}" for c in cols)
    print("\nshare of frames in each segment with a box of the expected class\n" + head)
    for r in results:
        print(f"{r['model'][:12]:12s} {r['imgsz']:5d} {r['mode']:5s} {r['conf']:4.2f} " + " ".join(
            f"{'-' if r[c] is None else f'{r[c]:.2f}':>13s}" for c in cols))
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
