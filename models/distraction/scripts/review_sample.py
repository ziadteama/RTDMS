#!/usr/bin/env python3
"""Label-quality review on a small random sample: make the review page, then score it.

    python scripts/review_sample.py make --labels D:/rtdms-data/openimages/labels_meta/train \
        --images D:/rtdms-data/openimages/images/train --n 120
    # open the HTML it prints, mark boxes, press "Save results" -> review_results.json
    python scripts/review_sample.py score --results review_results.json

The page is one local HTML file (images embedded, nothing uploaded). Boxes are coloured by
source: ground truth (green), COCO teacher (orange), open-vocabulary teacher (magenta). For
each box: correct / wrong class / not an object; per image: number of missed objects per class.
Scores: precision per source x class, and missed objects per image (a recall proxy).
"""

from __future__ import annotations

import argparse
import base64
import json
import random
from collections import defaultdict
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ["phone", "drink", "food", "hand"]
COLOURS = {"gt": (60, 200, 60), "teacher_coco": (0, 150, 255), "teacher_yoloe": (220, 60, 220)}


def make(args) -> None:
    rng = random.Random(args.seed)
    metas = sorted(Path(args.labels).glob("*.json"))
    # Stratify: equal share of images per class (an image can serve several classes).
    by_cls = defaultdict(list)
    for m in metas:
        for e in json.loads(m.read_text(encoding="utf8")):
            by_cls[e["cls"]].append(m)
    chosen: list[Path] = []
    for c in range(len(CLASSES)):
        pool = sorted(set(by_cls[c]) - set(chosen))
        chosen += rng.sample(pool, min(len(pool), args.n // len(CLASSES)))
    rng.shuffle(chosen)
    cards = []
    for m in chosen:
        boxes = json.loads(m.read_text(encoding="utf8"))
        img = cv2.imread(str(Path(args.images) / f"{m.stem}.jpg"))
        if img is None:
            continue
        h, w = img.shape[:2]
        s = 560 / max(h, w)
        img = cv2.resize(img, (round(w * s), round(h * s)))
        h, w = img.shape[:2]
        for i, e in enumerate(boxes):
            x1, y1, x2, y2 = (int(e["box"][0] * w), int(e["box"][1] * h),
                              int(e["box"][2] * w), int(e["box"][3] * h))
            col = COLOURS.get(e["src"], (255, 255, 255))
            cv2.rectangle(img, (x1, y1), (x2, y2), col, 2)
            cv2.putText(img, f"{i}", (x1 + 3, y1 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2)
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        cards.append({"id": m.stem, "img": base64.b64encode(enc).decode(),
                      "boxes": [{"i": i, "cls": CLASSES[e["cls"]], "src": e["src"],
                                 "conf": e["conf"]} for i, e in enumerate(boxes)]})
    out = Path(args.out)
    html = (ROOT / "scripts" / "review_template.html").read_text(encoding="utf8")
    out.write_text(html.replace("/*DATA*/[]", json.dumps(cards)), encoding="utf8", newline="\n")
    print(f"{len(cards)} images -> {out.resolve()}")


def score(args) -> None:
    res = json.loads(Path(args.results).read_text(encoding="utf8"))
    tally = defaultdict(lambda: {"correct": 0, "wrong_class": 0, "not_object": 0})
    missed = defaultdict(int)
    n_img = 0
    for card in res["cards"]:
        if not card.get("reviewed"):
            continue
        n_img += 1
        for b in card["boxes"]:
            if b.get("verdict"):
                tally[(b["src"], b["cls"])][b["verdict"]] += 1
        for c, k in (card.get("missed") or {}).items():
            missed[c] += int(k or 0)
    print(f"reviewed images: {n_img}")
    print(f"{'source':14s} {'class':6s} {'boxes':>5s} {'precision':>9s}  wrong-class  not-object")
    for (src, c), t in sorted(tally.items()):
        n = sum(t.values())
        print(f"{src:14s} {c:6s} {n:5d} {t['correct'] / n:9.2f}  {t['wrong_class']:11d}  "
              f"{t['not_object']:10d}")
    print("missed objects per reviewed image: " +
          ", ".join(f"{c} {missed[c] / max(1, n_img):.2f}" for c in CLASSES))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--labels", required=True, help="labels_meta/<split> from teacher_label.py")
    m.add_argument("--images", required=True)
    m.add_argument("--n", type=int, default=120)
    m.add_argument("--seed", type=int, default=7)
    m.add_argument("--out", default="review_sample.html")
    s = sub.add_parser("score")
    s.add_argument("--results", required=True)
    args = p.parse_args()
    (make if args.cmd == "make" else score)(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
