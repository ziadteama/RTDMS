#!/usr/bin/env python3
"""Hard-negative mining on SynDD: frames of NON-phone spans (normal driving and look-alikes) of
train / val drivers where the current detector fires a phone box become phone-free training
frames. In hand-at-face spans (hand on head, yawning) a drink / food box is a false alarm too.
TRAINING ENV (GPU).

    python scripts/mine_hard_negatives.py --weights D:/rtdms-data/runs/det_v2b_416/weights/best.pt \
        --out D:/rtdms-data/det_v2/syndd_hardneg

Other confident boxes (>= 0.5) of the classes that are not false alarms in that span are kept
as labels (a bottle in a cup holder during normal driving is real). Test drivers are never used.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rtdms_distraction import datasets as D  # noqa: E402

HAND_AT_FACE = {"neg_hand_on_head", "neg_yawning"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--weights", required=True)
    p.add_argument("--videos", default="D:/rtdms-data/public/syndd/A1")
    p.add_argument("--out", default="D:/rtdms-data/det_v2/syndd_hardneg")
    p.add_argument("--split-file", default=str(ROOT / "configs" / "syndd_split.json"))
    p.add_argument("--splits", default="train,val")
    p.add_argument("--every", type=float, default=1.0)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--imgsz", type=int, default=416)
    args = p.parse_args()

    from ultralytics import YOLO

    m = YOLO(args.weights)
    split = json.loads(Path(args.split_file).read_text(encoding="utf8"))
    use = set(args.splits.split(","))
    out = Path(args.out)
    stats, meta = Counter(), []
    for clip in D.syndd_clips(args.videos):
        if not (clip.label == "normal" or clip.label.startswith("neg_")):
            continue
        sp = split.get(clip.driver)
        if sp not in use:
            continue
        false_cls = {0} | ({1, 2} if clip.label in HAND_AT_FACE else set())
        for t, frame in clip.frames(args.every):
            stats["frames"] += 1
            h, w = frame.shape[:2]
            s = 960 / max(h, w)
            img = cv2.resize(frame, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
            r = m.predict(img, imgsz=args.imgsz, conf=args.conf, verbose=False)[0]
            cls = r.boxes.cls.cpu().numpy().astype(int)
            cf = r.boxes.conf.cpu().numpy()
            if not any(c in false_cls for c in cls):
                continue
            stats[f"fp_{clip.label}"] += 1
            keep = [(c, b) for c, b, q in zip(cls, r.boxes.xywhn.cpu().numpy(), cf, strict=True)
                    if c not in false_cls and q >= 0.5]
            stem = f"{clip.source}__{clip.driver}__{Path(clip.name).stem}_{int(t * 1000):07d}_hn"
            (out / "images" / sp).mkdir(parents=True, exist_ok=True)
            (out / "labels" / sp).mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out / "images" / sp / f"{stem}.jpg"), img,
                        [cv2.IMWRITE_JPEG_QUALITY, 90])
            (out / "labels" / sp / f"{stem}.txt").write_text(
                "".join(f"{c} {x:.6f} {y:.6f} {bw:.6f} {bh:.6f}\n" for c, (x, y, bw, bh) in keep),
                encoding="utf8")
            meta.append({"split": sp, "source": "syndd", "driver": clip.driver,
                         "label": clip.label, "image": f"{sp}/{stem}.jpg",
                         "boxes": json.dumps([int(c) for c, _ in keep])})
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "meta.csv", "w", newline="", encoding="utf8") as f:
        wr = csv.DictWriter(f, fieldnames=["split", "source", "driver", "label", "image",
                                           "boxes"])
        wr.writeheader()
        wr.writerows(meta)
    print(dict(stats), f"-> {len(meta)} hard negatives in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
