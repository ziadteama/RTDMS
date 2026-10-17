#!/usr/bin/env python3
"""Contact sheets + CSV for hand-checking auto-labelled test boxes (teacher labels).

    python scripts/hand_check_sheets.py --src D:/rtdms-data/det_v2/syndd --split test \
        --n 500 --out D:/rtdms-data/runs/overnight/hand_check

Stratified sample (phone at each ear, phone in hand, drinking, negatives), numbered tiles of the
driver area with the teacher's boxes (red phone, blue drink, green food), 50 per sheet. In the
CSV fill `box_ok` (y / n: every drawn box is on a real object of that class) and `missed`
(what real phone / drink / food has no box, or empty). Then
`python scripts/hand_check_sheets.py --score <csv>` prints label precision / recall.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

import cv2
import numpy as np

NAMES = {0: "phone", 1: "drink", 2: "food"}
COL = {0: (0, 0, 255), 1: (255, 160, 0), 2: (0, 200, 0)}
QUOTA = {"phone_right_ear": 110, "phone_left_ear": 110, "phone_in_hand": 90, "drinking": 45,
         "eating": 5, "neg_hand_on_head": 40, "normal": 40, "neg_talking": 20,
         "neg_yawning": 20, "neg_singing": 20}


def make(args) -> int:
    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = [r for r in csv.DictReader(open(src / "meta.csv", encoding="utf8"))
            if r["split"] == args.split]
    rng = random.Random(0)
    picked = []
    for lab, q in QUOTA.items():
        sel = [r for r in meta if r["label"] == lab]
        rng.shuffle(sel)
        picked += sel[:q]
    picked = picked[: args.n]
    rows, tiles = [], []
    for i, r in enumerate(picked, 1):
        img = cv2.imread(str(src / "images" / r["image"]))
        h, w = img.shape[:2]
        lab_p = (src / "labels" / r["image"]).with_suffix(".txt")
        boxes = [list(map(float, ln.split())) for ln in lab_p.read_text().splitlines() if ln]
        for c, x, y, bw, bh in boxes:
            cv2.rectangle(img, (int((x - bw / 2) * w), int((y - bh / 2) * h)),
                          (int((x + bw / 2) * w), int((y + bh / 2) * h)), COL[int(c)], 2)
        t = cv2.resize(img[:, int(0.3 * w):], (300, 240))
        cv2.rectangle(t, (0, 0), (300, 26), (0, 0, 0), -1)
        cv2.putText(t, f"#{i} {r['label'].replace('neg_', '')[:16]}", (4, 19), 0, 0.55,
                    (0, 255, 255), 1)
        tiles.append(t)
        rows.append({"id": i, "image": r["image"], "segment_label": r["label"],
                     "boxes": ";".join(NAMES[int(b[0])] for b in boxes) or "none",
                     "box_ok": "", "missed": "", "note": ""})
    for s in range(0, len(tiles), 50):
        chunk = tiles[s:s + 50] + [np.zeros((240, 300, 3), np.uint8)] * (50 - len(tiles[s:s + 50]))
        grid = np.vstack([np.hstack(chunk[k:k + 10]) for k in range(0, 50, 10)])
        cv2.imwrite(str(out / f"sheet_{s // 50 + 1:02d}_tiles_{s + 1}-{s + 50}.jpg"), grid,
                    [cv2.IMWRITE_JPEG_QUALITY, 88])
    with open(out / "hand_check.csv", "w", newline="", encoding="utf8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print(f"{len(rows)} tiles, {(len(rows) + 49) // 50} sheets -> {out}")
    return 0


def score(csv_path: Path) -> int:
    rows = list(csv.DictReader(open(csv_path, encoding="utf8")))
    done = [r for r in rows if r["box_ok"].strip()]
    with_box = [r for r in done if r["boxes"] != "none"]
    ok = sum(r["box_ok"].strip().lower().startswith("y") for r in with_box)
    missed = sum(bool(r["missed"].strip()) for r in done)
    print(json.dumps({"checked": len(done), "frames_with_boxes": len(with_box),
                      "label_precision": round(ok / len(with_box), 3) if with_box else None,
                      "frames_with_a_missed_object": missed}, indent=1))
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--src", default="D:/rtdms-data/det_v2/syndd")
    p.add_argument("--split", default="test")
    p.add_argument("--n", type=int, default=500)
    p.add_argument("--out", default="D:/rtdms-data/runs/overnight/hand_check")
    p.add_argument("--score", help="score a filled hand_check.csv")
    a = p.parse_args()
    raise SystemExit(score(Path(a.score)) if a.score else make(a))
