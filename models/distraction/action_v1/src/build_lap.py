"""v2 step 2: lap-crop data for the texting phone check (128 px, phone_in_hand / empty_hand).

train: lap crops from SynDD-train, syndd_fish, 3MDAD-train, EBDD-train.
  phone_in_hand = texting frames; empty_hand = normal / hand_on_face (incl. 3MDAD fatigue) /
  other frames, randomly cut to 2x the positives (seed 0).
val:   SynDD-val lap crops, same rule.
Weak labels: a texting frame whose phone left the crop is still called positive.

python build_lap.py -> data/phone_lap/{train,val}/{phone_in_hand,empty_hand}/*.jpg (hard links)
"""
import csv
import os
import random
from collections import Counter
from pathlib import Path

A = Path("D:/rtdms-data/action_v1")
OUT = A / "data" / "phone_lap"
NEG = ("normal", "hand_on_face", "other")


def rows(ds):
    p = A / "data" / "v2" / f"{ds}.csv"
    return list(csv.DictReader(open(p, encoding="utf8"))) if p.exists() else []


def link(rs, split, cls):
    d = OUT / split / cls
    d.mkdir(parents=True, exist_ok=True)
    for r in rs:
        dst = d / r["lap"].replace("/", "__")
        if not dst.exists():
            os.link(A / "data" / r["lap"], dst)


def main():
    rng = random.Random(0)
    train = [r for ds in ("syndd", "3mdad", "ebdd") for r in rows(ds) if r["split"] == "train"]
    train += rows("syndd_fish")
    val = [r for r in rows("syndd") if r["split"] == "val"]
    for split, rs in (("train", train), ("val", val)):
        pos = [r for r in rs if r["cls"] == "texting"]
        neg = [r for r in rs if r["cls"] in NEG]
        rng.shuffle(neg)
        neg = neg[: 2 * len(pos)]
        link(pos, split, "phone_in_hand")
        link(neg, split, "empty_hand")
        print(split, "phone_in_hand", len(pos), Counter(r["dataset"] for r in pos),
              "| empty_hand", len(neg), Counter(r["cls"] for r in neg))


if __name__ == "__main__":
    main()
