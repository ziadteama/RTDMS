#!/usr/bin/env python3
"""Collapse State Farm c0..c9 folders into safe/phone/eating ImageFolder layout.

Expects either:
  raw/imgs/train/c0..c9/*.jpg
or:
  raw/train/c0..c9/*.jpg

Writes:
  data/collapsed/{train,val}/{safe,phone,eating}/*.jpg
"""

from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

# State Farm competition class ids
MAP = {
    "c0": "safe",  # normal
    "c1": "phone",  # text right
    "c2": "phone",  # talk phone right
    "c3": "phone",  # text left
    "c4": "phone",  # talk phone left
    "c5": "safe",  # radio — deferred
    "c6": "eating",  # drinking
    "c7": "safe",  # reach behind
    "c8": "safe",  # hair/makeup
    "c9": "safe",  # passenger
}


def find_train_root(raw: Path) -> Path:
    for cand in (raw / "imgs" / "train", raw / "train", raw):
        if (cand / "c0").is_dir():
            return cand
    raise SystemExit(f"Could not find c0..c9 under {raw}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("data/collapsed"))
    p.add_argument("--val-ratio", type=float, default=0.15)
    p.add_argument("--max-per-class", type=int, default=0, help="0 = all; else cap per SF class")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    random.seed(args.seed)
    root = find_train_root(args.raw)
    buckets: dict[str, list[Path]] = {"safe": [], "phone": [], "eating": []}

    for cid, dest in MAP.items():
        folder = root / cid
        if not folder.is_dir():
            print(f"warn: missing {folder}")
            continue
        files = sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.png"))
        if args.max_per_class > 0:
            files = files[: args.max_per_class]
        buckets[dest].extend(files)

    if args.out.exists():
        shutil.rmtree(args.out)

    for split in ("train", "val"):
        for cls in buckets:
            (args.out / split / cls).mkdir(parents=True, exist_ok=True)

    counts = {k: len(v) for k, v in buckets.items()}
    print("collapsed counts:", counts)

    for cls, files in buckets.items():
        files = list(files)
        random.shuffle(files)
        n_val = max(1, int(len(files) * args.val_ratio)) if files else 0
        val, train = files[:n_val], files[n_val:]
        for i, src in enumerate(train):
            shutil.copy2(src, args.out / "train" / cls / f"{cls}_{i:06d}{src.suffix}")
        for i, src in enumerate(val):
            shutil.copy2(src, args.out / "val" / cls / f"{cls}_{i:06d}{src.suffix}")

    print("wrote", args.out.resolve())


if __name__ == "__main__":
    main()
