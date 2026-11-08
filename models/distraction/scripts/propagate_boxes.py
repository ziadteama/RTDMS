#!/usr/bin/env python3
"""Recover labels for frames the teacher missed inside SynDD phone-call / drinking spans, by
carrying the box over from neighbouring labelled frames (the phone stays at the ear; the hand
hides it from the teacher, which is exactly the case the detector must learn).

    python scripts/propagate_boxes.py --src D:/rtdms-data/det_v2/syndd \
        --out D:/rtdms-data/det_v2/syndd_prop --splits train,val

label_video_boxes.py sampled every --every s and wrote only frames with an agreeing box. Here,
for each missing sample time in a phone_right_ear / phone_left_ear / drinking span:
  boxes of the wanted class at the nearest labelled times before (tb) and after (ta):
    both within --max-gap s     -> linear interpolation
    only one, within --max-one s -> copy
  else the frame stays unlabelled (skipped).
Test drivers are never touched. Output: new frames only, same layout + meta.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rtdms_distraction import datasets as D  # noqa: E402

WANT = {"phone_right_ear": 0, "phone_left_ear": 0, "drinking": 1}


def _iou(a, b) -> float:
    """YOLO rows [cls, x, y, w, h] (normalised)."""
    ax1, ay1, ax2, ay2 = a[1] - a[3] / 2, a[2] - a[4] / 2, a[1] + a[3] / 2, a[2] + a[4] / 2
    bx1, by1, bx2, by2 = b[1] - b[3] / 2, b[2] - b[4] / 2, b[1] + b[3] / 2, b[2] + b[4] / 2
    iw, ih = max(0.0, min(ax2, bx2) - max(ax1, bx1)), max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    union = a[3] * a[4] + b[3] * b[4] - inter
    return inter / union if union > 0 else 0.0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--src", default="D:/rtdms-data/det_v2/syndd")
    p.add_argument("--videos", default="D:/rtdms-data/public/syndd/A1")
    p.add_argument("--out", default="D:/rtdms-data/det_v2/syndd_prop")
    p.add_argument("--split-file", default=str(ROOT / "configs" / "syndd_split.json"))
    p.add_argument("--splits", default="train,val")
    p.add_argument("--every", type=float, default=0.5)
    p.add_argument("--max-gap", type=float, default=2.0, help="drinks: interpolation window")
    p.add_argument("--max-gap-phone", type=float, default=1.5)
    p.add_argument("--min-iou", type=float, default=0.3, help="phones: neighbours must overlap")
    p.add_argument("--max-one-drink", type=float, default=0.5)
    args = p.parse_args()

    src, out = Path(args.src), Path(args.out)
    split = json.loads(Path(args.split_file).read_text(encoding="utf8"))
    use = set(args.splits.split(","))
    have: dict[str, dict[int, list]] = {}  # clip stem -> {ms: [boxes of wanted class]}
    for sp in use:
        for lp in (src / "labels" / sp).glob("*.txt"):
            m = re.match(r"(.+)_(\d{7})$", lp.stem)
            if not m:
                continue
            rows = [list(map(float, ln.split())) for ln in lp.read_text().splitlines() if ln]
            have.setdefault(m.group(1), {})[int(m.group(2))] = rows
    stats = Counter()
    meta = []
    for clip in D.syndd_clips(args.videos):
        if clip.label not in WANT or split.get(clip.driver) not in use:
            continue
        sp = split[clip.driver]
        stem0 = f"{clip.source}__{clip.driver}__{Path(clip.name).stem}"
        known = have.get(stem0, {})
        cls = WANT[clip.label]
        known = {ms: [r for r in rows if int(r[0]) == cls] for ms, rows in known.items()}
        known = {ms: rows for ms, rows in known.items() if rows}
        if not known:
            stats["clip_without_any_box"] += 1
            continue
        times = sorted(known)
        for t, frame in clip.frames(args.every):
            ms = int(t * 1000)
            if ms in known:
                continue
            stats["missing"] += 1
            # Phones: only between two boxes close in time that overlap (the phone stayed at the
            # ear). The first version also copied from one side and across moves: on the
            # contact sheet half the phone boxes sat at the ear after the phone had gone to the
            # hand. Drinks: interpolation, or a copy within max_one_drink.
            gap = args.max_gap_phone if cls == 0 else args.max_gap
            before = [x for x in times if x < ms and ms - x <= gap * 1000]
            after = [x for x in times if x > ms and x - ms <= gap * 1000]
            tb, ta = (before[-1] if before else None), (after[0] if after else None)
            one = args.max_one_drink if cls == 1 else 0.0
            if tb is not None and ta is not None and (
                    cls != 0 or _iou(known[tb][0], known[ta][0]) >= args.min_iou):
                a, b = known[tb][0], known[ta][0]
                w = (ms - tb) / (ta - tb)
                box = [cls] + [a[i] * (1 - w) + b[i] * w for i in range(1, 5)]
                how = "interp"
            elif tb is not None and ms - tb <= one * 1000:
                box, how = known[tb][0], "copy"
            elif ta is not None and ta - ms <= one * 1000:
                box, how = known[ta][0], "copy"
            else:
                stats["no_neighbour"] += 1
                continue
            h, w_ = frame.shape[:2]
            s = 960 / max(h, w_)
            img = cv2.resize(frame, (round(w_ * s), round(h * s)), interpolation=cv2.INTER_AREA)
            stem = f"{stem0}_{ms:07d}"
            (out / "images" / sp).mkdir(parents=True, exist_ok=True)
            (out / "labels" / sp).mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out / "images" / sp / f"{stem}.jpg"), img,
                        [cv2.IMWRITE_JPEG_QUALITY, 90])
            (out / "labels" / sp / f"{stem}.txt").write_text(
                f"{int(box[0])} {box[1]:.6f} {box[2]:.6f} {box[3]:.6f} {box[4]:.6f}\n",
                encoding="utf8")
            stats[f"added_{how}"] += 1
            meta.append({"split": sp, "source": "syndd", "driver": clip.driver,
                         "label": clip.label, "image": f"{sp}/{stem}.jpg",
                         "boxes": json.dumps([[int(box[0]), None, how]])})
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "meta.csv", "w", newline="", encoding="utf8") as f:
        wr = csv.DictWriter(f, fieldnames=["split", "source", "driver", "label", "image",
                                           "boxes"])
        wr.writeheader()
        wr.writerows(meta)
    print(dict(stats), Counter((m["split"], m["label"]) for m in meta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
