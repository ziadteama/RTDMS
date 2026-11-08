#!/usr/bin/env python3
"""Copy training outputs to the backup drive (run after every training run).

    python scripts/backup.py ear_cls_160_syndd mouth_cls_96_syndd
    python scripts/backup.py --all

Per run name: <root>/runs/<name>/ (weights, evals, contact sheets) and models/<name>_ncnn_model/.
Always: reports/ and the crop manifests. Destination: --dest, else $RTDMS_BACKUP, else
E:/rtdms-backup. Files are copied, never moved or deleted; an existing file is overwritten only
when the source is newer or a different size. Refuses to run if the destination drive is absent.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def copy_tree(src: Path, dest: Path) -> int:
    n = 0
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        d = dest / f.relative_to(src)
        st = f.stat()
        if d.is_file() and d.stat().st_size == st.st_size and d.stat().st_mtime >= st.st_mtime:
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, d)
        n += 1
    return n


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("runs", nargs="*", help="run names under <root>/runs")
    p.add_argument("--all", action="store_true", help="every run and every *_ncnn_model")
    p.add_argument("--dest", default=os.environ.get("RTDMS_BACKUP", "E:/rtdms-backup"))
    args = p.parse_args()

    dest = Path(args.dest)
    if not Path(dest.anchor).exists():
        print(f"backup drive {dest.anchor} not found; nothing copied", file=sys.stderr)
        return 2
    root = Path(yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))
                ["root"])
    names = sorted(d.name for d in (root / "runs").iterdir() if d.is_dir()) if args.all \
        else args.runs
    jobs = []
    for name in names:
        jobs.append((root / "runs" / name, dest / "runs" / name))
        ncnn = f"{name}_ncnn_model"
        jobs.append((ROOT / "models" / ncnn, dest / "models" / ncnn))
    if args.all:
        jobs += [(m, dest / "models" / m.name) for m in (ROOT / "models").glob("*_ncnn_model")]
    jobs.append((ROOT / "reports", dest / "reports"))
    for crops in root.glob("crops*"):
        for man in crops.glob("*/manifest.csv"):
            jobs.append((man.parent, dest / "crop_manifests" / crops.name / man.parent.name))
    total = 0
    for src, d in jobs:
        if not src.exists():
            continue
        if src.name in {"ear", "mouth"} and src.parent.name.startswith("crops"):
            d.mkdir(parents=True, exist_ok=True)  # manifests only, not the images
            shutil.copy2(src / "manifest.csv", d / "manifest.csv")
            total += 1
            continue
        n = copy_tree(src, d)
        total += n
        print(f"{n:5d} files  {src} -> {d}")
    print(f"backup done: {total} files copied to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
