"""Step 3: balance and build the action-classifier folders.

train = SynDD-train + syndd_fish + 3MDAD-train + EBDD-train, val = SynDD-val (balanced the same
way so top-1 means something). No class keeps more than 3x the smallest main class (main =
normal, call, texting, drinking, eating); larger classes are randomly subsampled (seed 0).
Test splits are not copied: eval reads them straight from the CSVs.

python build_cls.py [cap_factor=3]  -> data/cls/{train,val}/<class>/*.jpg (hard links)
"""
import csv
import json
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

A = Path("D:/rtdms-data/action_v1")
OUT = A / "data" / "cls"
MAIN = ("normal", "call", "texting", "drinking", "eating")
CLASSES = json.load(open(A / "class_map.json"))["classes"]


def rows(ds):
    p = A / "data" / f"{ds}.csv"
    return list(csv.DictReader(open(p, encoding="utf8"))) if p.exists() else []


def balance(items, factor, rng):
    by = defaultdict(list)
    for r in items:
        by[r["cls"]].append(r)
    smallest = min(len(by[c]) for c in MAIN if by[c])
    cap = factor * smallest
    out = []
    for c, rs in by.items():
        rng.shuffle(rs)
        out += rs[:cap]
    return out, smallest, cap


def link(rs, split):
    for r in rs:
        src = A / "data" / r["up"]
        d = OUT / split / r["cls"]
        d.mkdir(parents=True, exist_ok=True)
        dst = d / r["up"].replace("/", "__")
        if not dst.exists():
            os.link(src, dst)


def table(title, before, after):
    lines = [f"{title}", "| class | before | after |", "|---|---|---|"]
    for c in CLASSES:
        lines.append(f"| {c} | {before.get(c, 0)} | {after.get(c, 0)} |")
    return "\n".join(lines)


def main():
    factor = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    rng = random.Random(0)
    train = [r for ds in ("syndd", "3mdad", "ebdd") for r in rows(ds) if r["split"] == "train"]
    train += rows("syndd_fish")
    val = [r for r in rows("syndd") if r["split"] == "val"]
    report = []
    for split, rs in (("train", train), ("val", val)):
        bal, smallest, cap = balance(rs, factor, rng)
        link(bal, split)
        report.append(table(f"### {split} (smallest main class {smallest}, cap {cap})",
                            Counter(r["cls"] for r in rs), Counter(r["cls"] for r in bal)))
        by_ds = Counter((r["dataset"], r["cls"]) for r in bal)
        report.append("by dataset after balancing: " + ", ".join(
            f"{d}/{c}={n}" for (d, c), n in sorted(by_ds.items())))
    for ds in ("syndd", "3mdad", "ebdd", "dad"):
        t = Counter(r["cls"] for r in rows(ds) if r["split"] == "test")
        report.append(f"### {ds} test (not balanced): " + ", ".join(f"{c}={t.get(c, 0)}" for c in CLASSES))
    text = "\n\n".join(report)
    (A / "runs" / "balance.md").write_text(text, encoding="utf8")
    print(text)


if __name__ == "__main__":
    main()
