#!/usr/bin/env python3
"""Delete raw recordings whose frames have already been extracted (privacy).

    python scripts/purge_recordings.py                 # dry run: lists what WOULD be deleted
    python scripts/purge_recordings.py --delete        # asks you to type DELETE, then deletes

A video is eligible only if extract_frames.py has written frames from it (it appears as an
`origin` in a manifest.csv under the data root). Clips never extracted -- e.g. the S01 test
clip, which is never trained on -- are never touched. --keep protects more names.
The .json sidecar is kept (it holds no images); the extracted frames are kept.
Deletion is permanent: the files do not go to the recycle bin.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--dir", default=str(ROOT / "data" / "recordings"))
    p.add_argument("--keep", nargs="*", default=["S01_"], help="name substrings never deleted")
    p.add_argument("--delete", action="store_true", help="actually delete (asks to confirm)")
    args = p.parse_args()

    data_root = Path(yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(
        encoding="utf8"))["root"])
    extracted: dict[str, int] = {}
    for man in list(data_root.rglob("manifest.csv")) + list((ROOT / "data").rglob("manifest.csv")):
        with open(man, encoding="utf8") as f:
            for row in csv.DictReader(f):
                o = str(Path(row["origin"]).resolve())
                extracted[o] = extracted.get(o, 0) + 1

    videos = sorted(v for v in Path(args.dir).rglob("*") if v.suffix.lower() in (".mp4", ".avi",
                                                                              ".mkv", ".h264"))
    eligible, skipped = [], []
    for v in videos:
        n = extracted.get(str(v.resolve()), 0)
        if any(k in v.name for k in args.keep):
            skipped.append((v, "protected by --keep"))
        elif n == 0:
            skipped.append((v, "no extracted frames"))
        else:
            eligible.append((v, n))
    for v, why in skipped:
        print(f"  keep    {v.name}  ({why})")
    for v, n in eligible:
        print(f"  DELETE  {v.name}  ({n} frames extracted, {v.stat().st_size / 1e6:.0f} MB)")
    if not eligible:
        print("nothing to delete")
        return 0
    if not args.delete:
        print(f"\ndry run: {len(eligible)} file(s) would be deleted. Re-run with --delete.")
        return 0
    if not sys.stdin.isatty():
        print("refusing: confirmation needs an interactive terminal")
        return 1
    if input(f"\nPermanently delete {len(eligible)} raw recording(s)? Type DELETE: ") != "DELETE":
        print("aborted, nothing deleted")
        return 1
    for v, _ in eligible:
        v.unlink()
        print(f"  deleted {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
