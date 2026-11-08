"""Step 5 data: 128-px gray crops, phone_in_hand vs empty_hand.

Positives
  - object datasets: phone boxes, square crop of 2x the box side (takes in the hand), from
    Open Images (phone touching a hand box), Roboflow DMS_Project v2 ("phone"), ADMS_FINAL_3
    ("using iphone"), det_v2 SynDD / EBDD train-split frames (class 0 = phone);
  - our ear crops: the phone-side ear on call frames (SynDD, syndd_fish, 3MDAD train drivers).
Negatives
  - ear crops (both ears) on normal / hand_on_face / other / drinking / eating frames and the
    opposite ear on call frames (same train drivers);
  - Open Images hand boxes that touch no phone (2x square crop).
Validation = SynDD-val ear crops (same rules). Test ear crops come from the test splits in eval.

python build_phone.py   -> data/phone/{train,val}/{phone_in_hand,empty_hand}/*.jpg + counts
"""
import csv
import os
import random
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from extract import stretch

A = Path("D:/rtdms-data/action_v1")
DATA = Path("D:/rtdms-data")
OUT = A / "data" / "phone"
random.seed(0)


def yolo_boxes(txt):
    out = []
    if txt.exists():
        for line in txt.read_text().split("\n"):
            v = line.split()
            if len(v) >= 5:
                out.append((int(v[0]), *map(float, v[1:5])))
    return out


def crop_box(img, cx, cy, side):
    h, w = img.shape[:2]
    side = max(int(side), 16)
    x1, y1 = int(cx - side / 2), int(cy - side / 2)
    pad = cv2.copyMakeBorder(img, side, side, side, side, cv2.BORDER_REPLICATE)
    c = pad[y1 + side:y1 + 2 * side, x1 + side:x1 + 2 * side]
    return stretch(cv2.resize(c, (128, 128), interpolation=cv2.INTER_AREA))


def object_crops(img_dir, lab_dir, phone_ids, hand_id=None, need_hand=False, cap=None):
    pos, neg = [], []
    files = sorted(Path(img_dir).glob("*.jpg"))
    random.shuffle(files)
    for f in files:
        if cap and len(pos) >= cap:
            break
        bs = yolo_boxes(Path(lab_dir) / (f.stem + ".txt"))
        phones = [b for b in bs if b[0] in phone_ids]
        hands = [b for b in bs if hand_id is not None and b[0] == hand_id]
        if not phones and not (hands and len(neg) < (cap or 1e9)):
            continue
        g = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        h, w = g.shape

        def touch(a, b):
            return abs(a[1] - b[1]) * 2 < a[3] + b[3] + 0.02 and abs(a[2] - b[2]) * 2 < a[4] + b[4] + 0.02
        for p in phones:
            if need_hand and not any(touch(p, hb) for hb in hands):
                continue
            side = 2.0 * max(p[3] * w, p[4] * h)
            if side < 24:  # too small to see anything at 128 px
                continue
            pos.append(crop_box(g, p[1] * w, p[2] * h, side))
        for hb in hands:
            if any(touch(hb, p) for p in phones) or hb[3] * w < 20:
                continue
            neg.append(crop_box(g, hb[1] * w, hb[2] * h, 2.0 * max(hb[3] * w, hb[4] * h)))
    return pos, neg


def ear_rows(csvs, split):
    pos, neg = [], []
    for c in csvs:
        p = A / "data" / f"{c}.csv"
        if not p.exists():
            print("missing", p)
            continue
        for r in csv.DictReader(open(p, encoding="utf8")):
            if r["split"] != split:
                continue
            er, el = str(A / "data" / r["ear_r"]), str(A / "data" / r["ear_l"])
            if r["cls"] == "call":
                if r["side"] == "R":
                    pos.append(er)
                    neg.append(el)
                elif r["side"] == "L":
                    pos.append(el)
                    neg.append(er)
            elif r["cls"] in ("normal", "hand_on_face", "other", "drinking", "eating"):
                neg += [er, el]
    return pos, neg


def write(split, cls, items, tag):
    d = OUT / split / cls
    d.mkdir(parents=True, exist_ok=True)
    n = 0
    for k, it in enumerate(items):
        dst = d / f"{tag}_{k:06d}.jpg"
        if dst.exists():
            n += 1
            continue
        if isinstance(it, str):
            try:
                os.link(it, dst)
            except OSError:
                cv2.imwrite(str(dst), cv2.imread(it, cv2.IMREAD_GRAYSCALE))
        else:
            cv2.imwrite(str(dst), it, [cv2.IMWRITE_JPEG_QUALITY, 90])
        n += 1
    return n


def main():
    counts = Counter()
    # object datasets (train only)
    srcs = [
        ("oi", DATA / "openimages/images/train", DATA / "openimages/labels/train", {0}, 3, True, 6000),
        ("dms", DATA / "public/roboflow/dms_project/train/images",
         DATA / "public/roboflow/dms_project/train/labels", {3}, None, False, 3000),
        ("adms", DATA / "public/roboflow/adms_final_3/train/images",
         DATA / "public/roboflow/adms_final_3/train/labels", {4}, None, False, 3000),
        ("detv2syn", DATA / "det_v2/syndd/images/train", DATA / "det_v2/syndd/labels/train", {0},
         None, False, 4000),
        ("detv2ebdd", DATA / "det_v2/ebdd/images/train", DATA / "det_v2/ebdd/labels/train", {0},
         None, False, 2000),
    ]
    for tag, im, lab, ids, hand, need, cap in srcs:
        pos, neg = object_crops(im, lab, ids, hand, need, cap)
        counts[("train", "phone_in_hand", tag)] = write("train", "phone_in_hand", pos, tag)
        if neg:
            counts[("train", "empty_hand", tag)] = write("train", "empty_hand", neg[:cap], tag)
        print(tag, len(pos), len(neg), flush=True)
    # our ear crops
    pos, neg = ear_rows(["syndd", "syndd_fish", "3mdad", "ebdd"], "train")
    random.shuffle(neg)
    neg = neg[: 3 * len(pos)]
    counts[("train", "phone_in_hand", "ears")] = write("train", "phone_in_hand", pos, "ear")
    counts[("train", "empty_hand", "ears")] = write("train", "empty_hand", neg, "ear")
    vpos, vneg = ear_rows(["syndd"], "val")
    random.shuffle(vneg)
    vneg = vneg[: 3 * len(vpos)]
    counts[("val", "phone_in_hand", "ears")] = write("val", "phone_in_hand", vpos, "ear")
    counts[("val", "empty_hand", "ears")] = write("val", "empty_hand", vneg, "ear")
    for k, v in sorted(counts.items()):
        print(*k, v)
    tot = Counter()
    for (s, c, _), v in counts.items():
        tot[(s, c)] += v
    print(dict(tot))


if __name__ == "__main__":
    main()
