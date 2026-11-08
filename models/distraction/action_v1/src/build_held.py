"""Phase A2 only: build gray 128px crops after held_wrist.py and human wrist review.

No training. Test geometry is never included in the crop set. K is an explicit argument,
to avoid silently treating the provisional K in HELD_OBJECT.md as visually validated.
This script has NOT been executed in the restricted sandbox.
"""
# ruff: noqa: E402
import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict

sys.dont_write_bytecode = True

import cv2
import numpy as np
from held_wrist import DATA, OUT, VERSION, extract, target


def read_source(source, caps):
    if "image" in source:
        gray = cv2.imread(source["image"], cv2.IMREAD_GRAYSCALE)
    else:
        video = source["video"]
        if video not in caps:
            caps[video] = cv2.VideoCapture(video)
        cap = caps[video]
        cap.set(cv2.CAP_PROP_POS_FRAMES, source["frame"])
        ok, bgr = cap.read()
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if ok else None
    if gray is None:
        raise OSError(f"Cannot decode {source}")
    return gray


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=float, choices=(.75, 1.0, 1.5), required=True)
    ap.add_argument("--side", type=float, choices=(1.5, 1.75, 2.0), default=2.0)
    args = ap.parse_args()
    run = OUT / f"crops_k{args.k:g}_side{args.side:g}"
    # Refuse mixing stale crops into a future classifier directory.
    if run.exists():
        raise FileExistsError(f"{run} exists; archive it inside _held_data before rebuilding")
    complete = json.loads((OUT / "audit_complete.json").read_text(encoding="utf8"))
    if set(complete["datasets"]) != {"syndd", "3mdad", "ebdd", "dad"}:
        raise ValueError("Finish all four dataset wrist audits before building the crop set")
    inputs = [OUT / p for p in complete["geometry"]]
    assignments = {}
    for ds in ("syndd", "3mdad", "ebdd", "dad"):
        with open(DATA / f"action_v1/data/v2/{ds}.csv", encoding="utf8") as f:
            for r in csv.DictReader(f):
                key = (ds, r["driver"])
                if key in assignments and assignments[key] != r["split"]:
                    raise ValueError(f"Driver crosses splits: {key}")
                assignments[key] = r["split"]
    run.mkdir(parents=True)
    counts, negatives, samples, rows = Counter(), Counter(), defaultdict(list), []
    skipped_test = 0
    for p in inputs:
        data = json.loads(p.read_text(encoding="utf8"))
        if data["version"] != VERSION:
            raise ValueError(f"Unsupported geometry version: {p}")
        job = data["job"]
        ds, driver, split = job["dataset"], job["driver"], job["split"]
        if assignments[(ds, driver)] != split:
            raise ValueError(f"Split differs from original CSV: {p}")
        if split == "test":
            skipped_test += len(data["records"])
            continue
        if split not in ("train", "val") or (split == "val" and ds != "syndd"):
            raise ValueError(f"Unexpected tuning split: {p}")
        caps = {}
        try:
            for i, r in enumerate(data["records"]):
                if r["distance"] is None or r["distance"] > args.k:
                    continue
                label = target(r["label"], r["cls"])
                if label is None or label != r["target"]:
                    raise ValueError(f"Label mapping mismatch: {p}")
                gray = read_source(r["source"], caps)
                center = (np.array(r["mouth"]) + r["nearest_wrist"]) / 2
                side = args.side * r["face_height"]
                patch = extract.square(gray, center[0], center[1], side)
                crop = extract.stretch(cv2.resize(patch, (128, 128), interpolation=cv2.INTER_AREA))
                dest = run / split / label / f"{ds}_{job['clip']}_{i:06d}.jpg"
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not cv2.imwrite(str(dest), crop, [cv2.IMWRITE_JPEG_QUALITY, 90]):
                    raise OSError(dest)
                row = dict(path=str(dest.relative_to(OUT)), dataset=ds, driver=driver,
                           split=split, target=label, label=r["label"], clip=job["clip"],
                           t=r["t"], distance=r["distance"], face_source=r["face_source"],
                           source=json.dumps(r["source"]))
                rows.append(row)
                counts[(label, ds, split)] += 1
                if label == "empty_hand":
                    negatives[(ds, split, r["label"])] += 1
                samples[(split, label)].append(dest)
        finally:
            for cap in caps.values():
                cap.release()
    if rows:
        with open(run / "manifest.csv", "w", newline="", encoding="utf8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    balance = [dict(target=c, dataset=d, split=s, count=n)
               for (c, d, s), n in sorted(counts.items())]
    with open(run / "balance.csv", "w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=("target", "dataset", "split", "count"))
        writer.writeheader()
        writer.writerows(balance)
    rng, coverage = random.Random(23), {}
    for split in ("train", "val"):
        for label in ("cup_bottle", "food", "empty_hand"):
            paths = samples[(split, label)]
            selected = rng.sample(paths, min(48, len(paths)))
            canvas = np.zeros((6*150, 8*128), np.uint8)
            for i, path in enumerate(selected):
                y, x = divmod(i, 8)
                canvas[y*150:y*150+128, x*128:(x+1)*128] = cv2.imread(str(path), 0)
                cv2.putText(canvas, str(i), (x*128+2, y*150+145),
                            cv2.FONT_HERSHEY_SIMPLEX, .4, 255, 1)
            cv2.imwrite(str(run / f"sheet_{split}_{label}.jpg"), canvas,
                        [cv2.IMWRITE_JPEG_QUALITY, 80])
            (run / f"sheet_{split}_{label}.json").write_text(
                json.dumps([str(p.relative_to(OUT)) for p in selected], indent=2), encoding="utf8")
            coverage[f"{split}/{label}"] = dict(available=len(paths), shown=len(selected),
                                                  requirement_met=len(selected) >= 48)
    result = dict(k=args.k, side_face_heights=args.side, size=128,
                  normalization="gray; resize; D9 1-99 percentile stretch (flat span <8 unchanged)",
                  skipped_test_geometry_records=skipped_test, count=len(rows), sheets=coverage,
                  negatives=[dict(dataset=d, split=s, label=lab, count=n)
                             for (d, s, lab), n in sorted(negatives.items())])
    (run / "build.json").write_text(json.dumps(result, indent=2), encoding="utf8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
