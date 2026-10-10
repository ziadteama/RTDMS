#!/usr/bin/env python3
"""Extract labelled frames from a public dataset (or our own recordings) via its adapter.

    python scripts/extract_frames.py syndd --src D:/datasets/SynDD2 --every 0.5
    python scripts/extract_frames.py dmd --src D:/datasets/dmd --stream ir_body
    python scripts/extract_frames.py yawdd --src data/public/yawdd --every 1.0
    python scripts/extract_frames.py driver100 --src D:/datasets/100-Driver --cams Cam4

Writes <root>/<dataset>/images/all/<name>.jpg with provenance in the name
    <dataset>__<driver>__<session>__<label>__<t_ms>.jpg
(build_split.py groups by the driver field, so no person can land in two splits), and a
manifest.csv. Sampling is sparse (default 1 frame / 0.5 s) and near-duplicates are dropped:
consecutive frames carry no new information and are how leakage gets in.
Segments shorter than --trim * 2 are skipped; --trim seconds are cut from both ends of every
segment because behaviour boundaries in the annotations are approximate.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rtdms_distraction import datasets as D  # noqa: E402


def slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", str(s)).strip("-").lower() or "x"


class DupFilter:
    """Drop a frame whose 32x32 thumbnail barely differs from the last kept one."""

    def __init__(self, thresh: float):
        self.thresh = thresh
        self.last: np.ndarray | None = None

    def keep(self, img: np.ndarray) -> bool:
        g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (32, 32),
                       interpolation=cv2.INTER_AREA).astype(np.float32)
        if self.last is not None and float(np.abs(g - self.last).mean()) < self.thresh:
            return False
        self.last = g
        return True


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("dataset", choices=sorted(D.ADAPTERS))
    p.add_argument("--src", required=True, help="local dataset folder")
    p.add_argument("--out", help="default <root>/<dataset>/images/all")
    p.add_argument("--every", type=float, default=0.5, help="seconds between sampled frames")
    p.add_argument("--trim", type=float, default=0.5, help="seconds cut from segment ends")
    p.add_argument("--dup", type=float, default=2.0, help="near-duplicate threshold (gray lvl)")
    p.add_argument("--max-side", type=int, default=1024)
    p.add_argument("--labels", help="comma list of labels to keep (default all)")
    p.add_argument("--stream", default="ir_body", help="DMD stream")
    p.add_argument("--cams", default="Cam4", help="100-Driver cameras, comma list")
    args = p.parse_args()

    cfg = yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))
    out = Path(args.out) if args.out else Path(cfg["root"]) / args.dataset / "images" / "all"
    out.mkdir(parents=True, exist_ok=True)
    kw = {"dmd": {"stream": args.stream},
          "driver100": {"cams": tuple(args.cams.split(","))}}.get(args.dataset, {})
    items = D.ADAPTERS[args.dataset](args.src, **kw)
    keep_labels = set(args.labels.split(",")) if args.labels else None
    if keep_labels:
        items = [i for i in items if i.label in keep_labels]
    print(f"{args.dataset}: {len(items)} items, {len({i.driver for i in items})} drivers, "
          f"labels {dict(Counter(i.label for i in items))}")

    rows, counts = [], Counter()

    def save(img, name, item, t):
        h, w = img.shape[:2]
        s = args.max_side / max(h, w)
        if s < 1:
            img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(out / name), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        rows.append({"file": name, "source": item.source, "driver": item.driver,
                     "label": item.label, "view": item.view, "t": t,
                     "origin": str(getattr(item, "video", getattr(item, "image", "")))})
        counts[item.label] += 1

    stills = [i for i in items if isinstance(i, D.Still)]
    for it in stills:
        img = cv2.imread(str(it.image))
        if img is not None:
            save(img, f"{args.dataset}__{slug(it.driver)}__{slug(it.view)}__{it.label}__"
                      f"{slug(it.image.stem)}.jpg", it, 0.0)

    by_video: dict[Path, list[D.Segment]] = {}
    for it in items:
        if isinstance(it, D.Segment):
            by_video.setdefault(it.video, []).append(it)
    for video, segs in by_video.items():
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            print(f"  SKIP (cannot open) {video}")
            continue
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        for seg in sorted(segs, key=lambda s: s.start_s):
            a, b = seg.start_s + args.trim, seg.end_s - args.trim
            if b <= a:
                continue
            dup = DupFilter(args.dup)
            for t in np.arange(a, b, args.every):
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
                ok, img = cap.read()
                if not ok:
                    break
                if not dup.keep(img):
                    continue
                save(img, f"{args.dataset}__{slug(seg.driver)}__{slug(video.stem)}__"
                          f"{seg.label}__{int(t * 1000):08d}.jpg", seg, round(float(t), 3))
        cap.release()

    man = out.parent.parent / "manifest.csv"
    new = not man.is_file()
    with open(man, "a", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "source", "driver", "label", "view", "t",
                                          "origin"])
        if new:
            w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} frames to {out}: {dict(counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
