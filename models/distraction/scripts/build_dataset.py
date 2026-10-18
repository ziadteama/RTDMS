#!/usr/bin/env python3
"""Assemble the training dataset (Ultralytics list files + data.yaml), split by DRIVER.

    python scripts/build_dataset.py --name v1 \
        --fixed D:/rtdms-data/converted/oiv \
        --drivers D:/rtdms-data/converted/syndd \
        --background D:/rtdms-data/converted/yawdd --bg-fraction 0.1

--fixed       sources with their own train/val/test folders (Open Images: independent photos,
              no person appears twice, so the official split is kept).
--drivers     sources whose frames are named <dataset>__<driver>__...: whole drivers are
              assigned to train / val / test (test drivers are never seen in training).
--background  driver sources with NO objects (YawDD normal/talking/singing): train drivers'
              frames join training as background images (capped at --bg-fraction of train);
              test drivers' frames are kept for false-alarm testing only.
Images are referenced in place (labels found by Ultralytics' images/ -> labels/ rule); nothing
is copied. The split refuses to write anything if a driver lands in two splits.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ("train", "val", "test")


def label_path(im: Path) -> Path:
    """Ultralytics' rule: last '/images/' in the path -> '/labels/', suffix -> .txt."""
    s = str(im)
    a, b = f"{os.sep}images{os.sep}", f"{os.sep}labels{os.sep}"
    i = s.rfind(a)
    return Path((s[:i] + b + s[i + len(a):]) if i >= 0 else s).with_suffix(".txt")


def driver_of(p: Path) -> str:
    parts = p.stem.split("__")
    return f"{parts[0]}/{parts[1]}" if len(parts) >= 3 else "unknown"


def class_counts(images: list[Path], classes: list[str]) -> dict[str, int]:
    c = Counter()
    for im in images:
        lab = label_path(im)
        if lab.is_file():
            for line in lab.read_text(encoding="utf8").split("\n"):
                if line.strip():
                    c[classes[int(line.split()[0])]] += 1
        else:
            c["(no label file)"] += 1
    return dict(c)


def split_drivers(images: list[Path], test_frac: float, val_frac: float, rng):
    by = defaultdict(list)
    for im in images:
        by[driver_of(im)].append(im)
    drivers = sorted(by)
    rng.shuffle(drivers)
    if len(drivers) < 3:
        raise SystemExit(f"only {len(drivers)} drivers ({drivers}); need >= 3 for a split")
    n_test = max(1, round(len(drivers) * test_frac))
    n_val = max(1, round(len(drivers) * val_frac))
    parts = {"test": drivers[:n_test], "val": drivers[n_test:n_test + n_val],
             "train": drivers[n_test + n_val:]}
    return parts, by


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--name", required=True)
    p.add_argument("--fixed", nargs="*", default=[])
    p.add_argument("--drivers", nargs="*", default=[])
    p.add_argument("--background", nargs="*", default=[])
    p.add_argument("--bg-fraction", type=float, default=0.1)
    p.add_argument("--test-drivers", type=float, default=0.2, help="fraction of drivers")
    p.add_argument("--val-drivers", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=1337)
    args = p.parse_args()

    cfg = yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))
    classes = cfg["classes"]
    out = Path(cfg["root"]) / "datasets" / args.name
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    lists: dict[str, list[Path]] = {s: [] for s in SPLITS}
    report: dict = {"sources": {}, "drivers": {}}
    owner: dict[str, str] = {}

    for src in map(Path, args.fixed):
        for s in SPLITS:
            imgs = sorted((src / "images" / s).glob("*.jpg"))
            lists[s] += imgs
            report["sources"].setdefault(src.name, {})[s] = len(imgs)

    def assign(src: Path, background: bool):
        imgs = sorted((src / "images" / "all").glob("*.jpg"))
        parts, by = split_drivers(imgs, args.test_drivers, args.val_drivers, rng)
        for s, ds in parts.items():
            for d in ds:
                if d in owner and owner[d] != s:
                    raise SystemExit(f"LEAK: driver {d} in both {owner[d]} and {s}")
                owner[d] = s
        report["drivers"][src.name] = {s: ds for s, ds in parts.items()}
        return parts, by

    for src in map(Path, args.drivers):
        parts, by = assign(src, False)
        for s, ds in parts.items():
            n = sum(len(by[d]) for d in ds)
            lists[s] += [im for d in ds for im in by[d]]
            report["sources"].setdefault(src.name, {})[s] = n

    fa_test: list[Path] = []
    for src in map(Path, args.background):
        parts, by = assign(src, True)
        pool = [im for d in parts["train"] for im in by[d]]
        rng.shuffle(pool)
        cap = int(args.bg_fraction * max(1, len(lists["train"])))
        lists["train"] += pool[:cap]
        fa_test += [im for d in parts["test"] + parts["val"] for im in by[d]]
        report["sources"].setdefault(src.name, {}).update(
            {"train_background": min(cap, len(pool)), "false_alarm_test": len(fa_test)})

    for s in SPLITS:
        (out / f"{s}.txt").write_text("\n".join(str(i) for i in lists[s]) + "\n",
                                      encoding="utf8", newline="\n")
    if fa_test:
        (out / "false_alarm_test.txt").write_text("\n".join(map(str, fa_test)) + "\n",
                                                  encoding="utf8", newline="\n")
    data = {"path": str(out), "train": "train.txt", "val": "val.txt", "test": "test.txt",
            "names": dict(enumerate(classes))}
    (out / "data.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf8",
                                   newline="\n")
    report["images"] = {s: len(v) for s, v in lists.items()}
    report["boxes_per_class"] = {s: class_counts(v, classes) for s, v in lists.items()}
    (out / "split_report.json").write_text(json.dumps(report, indent=2), encoding="utf8",
                                           newline="\n")
    print(json.dumps({k: report[k] for k in ("sources", "images", "boxes_per_class")}, indent=2))
    print(f"-> {out / 'data.yaml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
