#!/usr/bin/env python3
"""Assemble the phone / drink / food detector dataset (v2) from every boxed source.

    python scripts/build_det_v2.py --out D:/rtdms-data/det_v2/merged \
        --yolo D:/rtdms-data/det_v2/syndd --yolo D:/rtdms-data/det_v2/ebdd \
        --roboflow D:/rtdms-data/public/roboflow/dms_project \
        --roboflow D:/rtdms-data/public/roboflow/adms_final_3

Sources
  --yolo DIR       our auto-labelled video frames: DIR/{images,labels}/{train,val,test}, classes
                   0 phone / 1 drink / 2 food (scripts/label_video_boxes.py), split by driver
  Open Images      <root>/openimages/{images,labels}/{split} (GT + teacher fills); hand (3) dropped
  --roboflow DIR   a Roboflow YOLO export (data.yaml + {train,valid,test}/{images,labels});
                   class NAMES are mapped (ROBOFLOW_MAP), unmapped classes dropped. Roboflow's own
                   split is kept (it is image-level; these sets have no driver ids).

Mixing IR and colour: --gray-share of the colour TRAIN images get a gray x3 copy as well.
Occlusion: --occlude-share of train images with a phone get a copy with a real hand crop (Open
Images GT hand boxes) pasted over 30-60 % of each phone box, entering from a random side, with a
feathered edge; the phone box is kept as the full phone. Val / test are never augmented.
Images are hard-linked when possible (same drive), else copied. Labels are rewritten.
Output: OUT/{images,labels}/{train,val,test}, OUT/data.yaml, OUT/summary.json.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
NAMES = ["phone", "drink", "food"]
OI_MAP = {0: 0, 1: 1, 2: 2}  # 3 = hand: dropped
ROBOFLOW_MAP = {"phone": 0, "cell phone": 0, "cellphone": 0, "mobile": 0, "mobile phone": 0,
                "using iphone": 0, "using phone": 0, "iphone": 0,
                "drink": 1, "drinking": 1, "bottle": 1, "cup": 1, "can": 1,
                "food": 2, "eating": 2}
SPLITS = {"train": "train", "valid": "val", "val": "val", "test": "test"}
IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def read_labels(p: Path) -> list[list[float]]:
    if not p.is_file():
        return []
    return [list(map(float, ln.split()[:5])) for ln in p.read_text(encoding="utf8").splitlines()
            if len(ln.split()) >= 5]


def write_labels(p: Path, rows) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(f"{int(c)} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n" for c, x, y, w, h in rows),
                 encoding="utf8")


def place(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def is_gray(img: np.ndarray) -> bool:
    if img.ndim == 2:
        return True
    s = img[::8, ::8].astype(np.int16)
    return float(np.abs(s[..., 0] - s[..., 2]).mean()) < 3 and \
        float(np.abs(s[..., 1] - s[..., 2]).mean()) < 3


def hand_bank(root: Path, n: int, rng: random.Random) -> list[np.ndarray]:
    """Real hands: Open Images GT 'Human hand' boxes (labels_gt class 3), at least 40 px."""
    oi = root / "openimages"
    files = sorted((oi / "labels_gt" / "train").glob("*.txt"))
    rng.shuffle(files)
    out = []
    for lp in files:
        hands = [r for r in read_labels(lp) if int(r[0]) == 3]
        if not hands:
            continue
        img = cv2.imread(str(oi / "images" / "train" / f"{lp.stem}.jpg"))
        if img is None:
            continue
        h, w = img.shape[:2]
        for _, x, y, bw, bh in hands:
            x1, y1 = int((x - bw / 2) * w), int((y - bh / 2) * h)
            x2, y2 = int((x + bw / 2) * w), int((y + bh / 2) * h)
            if min(x2 - x1, y2 - y1) >= 40:
                out.append(img[max(0, y1):y2, max(0, x1):x2].copy())
        if len(out) >= n:
            break
    return out


def occlude(img: np.ndarray, rows, hands, rng: random.Random) -> np.ndarray:
    out = img.copy()
    h, w = img.shape[:2]
    gray = is_gray(img)
    for c, x, y, bw, bh in rows:
        if int(c) != 0 or not hands:
            continue
        pw, ph = bw * w, bh * h
        cover = rng.uniform(0.3, 0.6)
        hand = hands[rng.randrange(len(hands))]
        # hand size ~ the phone's, so `cover` of the phone is hidden when shifted in
        sw, sh = max(8, int(pw * rng.uniform(0.9, 1.4))), max(8, int(ph * rng.uniform(0.9, 1.4)))
        patch = cv2.resize(hand, (sw, sh))
        if gray:
            patch = cv2.cvtColor(cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        side = rng.choice(("left", "right", "top", "bottom"))
        cx, cy = x * w, y * h
        if side in ("left", "right"):
            dx = (pw / 2 + sw / 2 - cover * pw) * (-1 if side == "left" else 1)
            px, py = cx + dx - sw / 2, cy - sh / 2 + rng.uniform(-0.2, 0.2) * ph
        else:
            dy = (ph / 2 + sh / 2 - cover * ph) * (-1 if side == "top" else 1)
            px, py = cx - sw / 2 + rng.uniform(-0.2, 0.2) * pw, cy + dy - sh / 2
        x0, y0 = int(px), int(py)
        xa, ya, xb, yb = max(0, x0), max(0, y0), min(w, x0 + sw), min(h, y0 + sh)
        if xb <= xa or yb <= ya:
            continue
        p = patch[ya - y0:yb - y0, xa - x0:xb - x0].astype(np.float32)
        # Match the hand's brightness / contrast to the area it covers (plus a little: skin is
        # usually brighter than a phone), so the model cannot learn the pasted patch itself.
        roi0 = out[ya:yb, xa:xb].astype(np.float32)
        p = (p - p.mean()) / (p.std() + 1e-3) * max(roi0.std(), 12.0) + roi0.mean() * 1.1
        p = np.clip(p, 0, 255)
        mask = np.zeros(p.shape[:2], np.float32)
        cv2.ellipse(mask, (p.shape[1] // 2, p.shape[0] // 2),
                    (max(1, p.shape[1] // 2), max(1, p.shape[0] // 2)), 0, 0, 360, 1.0, -1)
        k = max(3, (min(p.shape[:2]) // 6) | 1)
        mask = cv2.GaussianBlur(mask, (k, k), 0)[..., None]
        roi = out[ya:yb, xa:xb].astype(np.float32)
        out[ya:yb, xa:xb] = (mask * p + (1 - mask) * roi).astype(np.uint8)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--out", required=True)
    p.add_argument("--yolo", action="append", default=[])
    p.add_argument("--roboflow", action="append", default=[])
    p.add_argument("--no-openimages", action="store_true")
    p.add_argument("--gray-share", type=float, default=0.3)
    p.add_argument("--occlude-share", type=float, default=0.5)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    rng = random.Random(args.seed)
    root = Path(yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))
                ["root"])
    out = Path(args.out)
    items: list[tuple[str, str, Path, list]] = []  # (source, split, image, rows)

    for d in map(Path, args.yolo):
        for split in ("train", "val", "test"):
            for img in sorted((d / "images" / split).glob("*.jpg")):
                items.append((d.name, split, img, read_labels(d / "labels" / split /
                                                                f"{img.stem}.txt")))
    if not args.no_openimages:
        oi = root / "openimages"
        for split in ("train", "val", "test"):
            for img in sorted((oi / "images" / split).glob("*.jpg")):
                rows = [[OI_MAP[int(r[0])], *r[1:]] for r in
                        read_labels(oi / "labels" / split / f"{img.stem}.txt")
                        if int(r[0]) in OI_MAP]
                items.append(("openimages", split, img, rows))
    for d in map(Path, args.roboflow):
        names = yaml.safe_load((d / "data.yaml").read_text(encoding="utf8"))["names"]
        names = [names[i] for i in sorted(names)] if isinstance(names, dict) else list(names)
        cmap = {i: ROBOFLOW_MAP[n.strip().lower()] for i, n in enumerate(names)
                if n.strip().lower() in ROBOFLOW_MAP}
        print(f"{d.name}: classes {names} -> {[(names[i], NAMES[c]) for i, c in cmap.items()]}")
        for rf_split, split in SPLITS.items():
            for img in sorted((d / rf_split / "images").glob("*")):
                if img.suffix.lower() not in IMG_EXT:
                    continue
                rows = [[cmap[int(r[0])], *r[1:]] for r in
                        read_labels(d / rf_split / "labels" / f"{img.stem}.txt")
                        if int(r[0]) in cmap]
                items.append((d.name, split, img, rows))

    stats = Counter()
    train_phone, train_colour = [], []
    for src, split, img, rows in items:
        stem = f"{src}__{img.stem}"
        place(img, out / "images" / split / f"{stem}{img.suffix.lower()}")
        write_labels(out / "labels" / split / f"{stem}.txt", rows)
        stats[(src, split, "images")] += 1
        for r in rows:
            stats[(src, split, NAMES[int(r[0])])] += 1
        if split == "train":
            if any(int(r[0]) == 0 for r in rows):
                train_phone.append((src, img, rows))
            if src not in ("syndd",):
                train_colour.append((src, img, rows))

    # gray copies of colour train images (IR look); skip the ones that are already gray
    n_gray = 0
    for src, img, rows in rng.sample(train_colour, int(args.gray_share * len(train_colour))):
        im = cv2.imread(str(img))
        if im is None or is_gray(im):
            continue
        g = cv2.cvtColor(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        stem = f"{src}__{img.stem}__gray"
        cv2.imwrite(str(out / "images" / "train" / f"{stem}.jpg"), g,
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        write_labels(out / "labels" / "train" / f"{stem}.txt", rows)
        n_gray += 1

    # occluded copies of phone images (hand over 30-60 % of the phone)
    hands = hand_bank(root, 3000, rng)
    n_occ = 0
    for src, img, rows in rng.sample(train_phone, int(args.occlude_share * len(train_phone))):
        im = cv2.imread(str(img))
        if im is None:
            continue
        stem = f"{src}__{img.stem}__occ"
        cv2.imwrite(str(out / "images" / "train" / f"{stem}.jpg"), occlude(im, rows, hands, rng),
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        write_labels(out / "labels" / "train" / f"{stem}.txt", rows)
        n_occ += 1

    (out / "data.yaml").write_text(yaml.safe_dump({
        "path": str(out), "train": "images/train", "val": "images/val", "test": "images/test",
        "names": dict(enumerate(NAMES))}, sort_keys=False), encoding="utf8")
    summary = {"by_source": {f"{a}/{b}/{c}": v for (a, b, c), v in sorted(stats.items())},
               "gray_copies": n_gray, "occluded_copies": n_occ, "hand_bank": len(hands)}
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf8")
    for k, v in summary["by_source"].items():
        print(f"  {k:40s} {v}")
    print(f"gray copies {n_gray}, occluded copies {n_occ} (hand bank {len(hands)}) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
