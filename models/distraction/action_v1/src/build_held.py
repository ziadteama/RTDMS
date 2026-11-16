"""Phase A2 only: build gray 128px crops after held_wrist.py and human wrist review.

No training. Test geometry is never included in the crop set. K is an explicit argument,
to avoid silently treating the provisional K in HELD_OBJECT.md as visually validated.
Progress is appended to _held_data/LIVE.log; no classifier is trained here.
"""

# ruff: noqa: E402
import argparse
import csv
import json
import random
import sys
import time
from collections import Counter

sys.dont_write_bytecode = True

import cv2
import numpy as np
from held_geometry import hand_geometry
from held_wrist import DATA, OUT, extract, log, target


def read_source(source, caps):
    if "image" in source:
        gray = cv2.imread(source["image"], cv2.IMREAD_GRAYSCALE)
    else:
        video = source["video"]
        if video not in caps:
            caps[video] = cv2.VideoCapture(video, cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
        cap = caps[video]
        current = round(cap.get(cv2.CAP_PROP_POS_FRAMES))
        delta = source["frame"] - current
        if 0 <= delta <= 90:
            for _ in range(delta):
                if not cap.grab():
                    raise OSError(f"Cannot advance to {source}")
        else:
            cap.set(cv2.CAP_PROP_POS_FRAMES, source["frame"])
        ok, bgr = cap.read()
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if ok else None
    if gray is None:
        raise OSError(f"Cannot decode {source}")
    return gray


RUN_NAME = "crops_loose_h035_k125"
H, K, MIN_GAP = 0.35, 1.25, 0.3


def candidate(r):
    if r["mouth"] is None:
        return None
    kp, mouth = np.asarray(r["kp"], float), np.asarray(r["mouth"], float)
    loose = hand_geometry(kp, mouth, r["face_height"], H)
    if loose["distance"] is None or loose["distance"] > K:
        return None
    tight = hand_geometry(kp, mouth, r["face_height"], 0)
    return loose, tight


def square_cover(gray, crop):
    """Keep nominal centre and cover both endpoints; replicate-pad outside the image."""
    side = max(2, int(np.ceil(crop["side"])))
    cx, cy = crop["center"]
    x, y = int(np.floor(cx - side / 2)), int(np.floor(cy - side / 2))
    height, width = gray.shape
    padding = [max(0, -x), max(0, -y), max(0, x + side - width), max(0, y + side - height)]
    left, top, right, bottom = padding
    padded = cv2.copyMakeBorder(gray, top, bottom, left, right, cv2.BORDER_REPLICATE)
    patch = padded[y + top : y + top + side, x + left : x + left + side]
    assert patch.shape == (side, side)
    return extract.stretch(cv2.resize(patch, (128, 128), interpolation=cv2.INTER_AREA)), padding


def write_csv(path, rows, fields=None):
    with open(path, "w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_class_sheets(run, rows):
    rng, coverage = random.Random(27), {}
    for split in ("train", "val"):
        for label in ("cup_bottle", "food", "empty_hand"):
            for subset in ("tight", "loose_only"):
                pool = [
                    r
                    for r in rows
                    if r["split"] == split
                    and r["target"] == label
                    and bool(r["tight"]) == (subset == "tight")
                ]
                selected = rng.sample(pool, min(48, len(pool)))
                canvas = np.zeros(
                    (40 + max(1, int(np.ceil(len(selected) / 6))) * 232, 6 * 192, 3), np.uint8
                )
                title = f"{split} {label} {subset}: {len(selected)} / {len(pool)} (seed 27)"
                cv2.putText(canvas, title, (4, 27), 0, 0.6, (255, 255, 255), 1)
                for i, r in enumerate(selected):
                    image = cv2.imread(str(OUT / r["path"]), 0)
                    tile = np.zeros((232, 192, 3), np.uint8)
                    tile[:192] = cv2.cvtColor(cv2.resize(image, (192, 192)), cv2.COLOR_GRAY2BGR)
                    cv2.putText(
                        tile, f"{i} {r['driver']}"[:30], (2, 207), 0, 0.34, (255, 255, 255), 1
                    )
                    cv2.putText(
                        tile,
                        f"d0={r['dist_h0']:.2f} d35={r['dist_h035']:.2f}",
                        (2, 224),
                        0,
                        0.34,
                        (255, 255, 255),
                        1,
                    )
                    y, x = divmod(i, 6)
                    canvas[40 + y * 232 : 40 + (y + 1) * 232, x * 192 : (x + 1) * 192] = tile
                stem = f"sheet_{split}_{label}_{subset}"
                if not cv2.imwrite(
                    str(run / f"{stem}.jpg"), canvas, [cv2.IMWRITE_JPEG_QUALITY, 85]
                ):
                    raise OSError(stem)
                (run / f"{stem}.json").write_text(json.dumps(selected, indent=2), encoding="utf8")
                coverage[f"{split}/{label}/{subset}"] = dict(
                    available=len(pool), shown=len(selected), tile_image_px=192, fixed_seed=27
                )
    return coverage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--h", type=float, choices=(0.35,), default=H)
    ap.add_argument("--k", type=float, choices=(1.25,), default=K)
    ap.add_argument("--min-gap", type=float, choices=(0.3,), default=MIN_GAP)
    ap.parse_args()
    cv2.setNumThreads(1)
    log(
        "Starting loose crop build: h=.35 K=1.25, mouth fallback, >=.3s spacing; "
        "train + SynDD-val only; expected 10-25 minutes, no training"
    )
    complete = json.loads((OUT / "geometry_v2/geometry_complete.json").read_text(encoding="utf8"))
    assert set(complete["datasets"]) == {"syndd", "3mdad", "ebdd", "dad"}
    # Use corrected mouth records, independent of the superseded grid selection.
    inputs = sorted((OUT / "geometry_v2/base").glob("*.json"))
    assert len(inputs) == len(complete["geometry"])
    assignments = {}
    for ds in complete["datasets"]:
        with open(DATA / f"action_v1/data/v2/{ds}.csv", encoding="utf8") as f:
            for r in csv.DictReader(f):
                key = ds, r["driver"]
                if key in assignments and assignments[key] != r["split"]:
                    raise ValueError(f"Driver crosses splits: {key}")
                assignments[key] = r["split"]
    run = OUT / RUN_NAME
    if run.exists():
        raise FileExistsError(f"{run} exists; do not mix a new build into existing artifacts")
    run.mkdir()
    before, after, neg_before, neg_after = Counter(), Counter(), Counter(), Counter()
    rows, excluded_test, excluded_tight_not_loose = [], 0, 0
    last_log = time.monotonic()
    for job_index, path in enumerate(inputs, 1):
        data = json.loads(path.read_text(encoding="utf8"))
        job = data["job"]
        ds, split, driver = job["dataset"], job["split"], job["driver"]
        assert assignments[(ds, driver)] == split
        if split == "test":
            excluded_test += len(data["records"])
            continue
        assert split in ("train", "val") and (split != "val" or ds == "syndd")
        caps, last_t = {}, -float("inf")
        try:
            for i, r in enumerate(sorted(data["records"], key=lambda r: r["t"])):
                label = target(r["label"], r["cls"])
                assert label is not None and label == r["target"]
                found = candidate(r)
                if found is None:
                    if r["mouth"] is not None:
                        geo0 = hand_geometry(
                            np.asarray(r["kp"]), np.asarray(r["mouth"]), r["face_height"], 0
                        )
                        excluded_tight_not_loose += (
                            geo0["distance"] is not None and geo0["distance"] <= 1
                        )
                    continue
                geo, geo0 = found
                tight = int(geo0["distance"] <= 1)
                key, negkey = (label, ds, split), (ds, split, r["label"])
                before[(*key, "loose")] += 1
                before[(*key, "tight")] += tight
                if label == "empty_hand":
                    neg_before[(*negkey, "loose")] += 1
                    neg_before[(*negkey, "tight")] += tight
                if r["t"] - last_t < MIN_GAP - 1e-6:
                    continue
                last_t = r["t"]
                gray = read_source(r["source"], caps)
                crop, padding = square_cover(gray, geo["crop"])
                dest = run / split / label / f"{ds}_{job['clip']}_{i:06d}.jpg"
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not cv2.imwrite(str(dest), crop, [cv2.IMWRITE_JPEG_QUALITY, 90]):
                    raise OSError(dest)
                kp = np.asarray(r["kp"])
                w = geo["wrist_id"]
                e = w - 2

                def conf(index, points=kp):
                    return float(points[index, 2]) if np.isfinite(points[index, 2]) else ""

                row = dict(
                    path=str(dest.relative_to(OUT)),
                    dataset=ds,
                    split=split,
                    driver=driver,
                    clip=job["clip"],
                    t=r["t"],
                    original_label=r["label"],
                    label=r["label"],
                    target=label,
                    face_source=r["face_source"],
                    dist_h0=geo0["distance"],
                    dist_h035=geo["distance"],
                    tight=tight,
                    subset="tight" if tight else "loose_only",
                    wrist_id=w,
                    elbow_id=e,
                    wrist_conf=conf(w),
                    elbow_conf=conf(e),
                    elbow_usable=int(geo["elbow_usable"]),
                    left_wrist_conf=conf(9),
                    right_wrist_conf=conf(10),
                    left_elbow_conf=conf(7),
                    right_elbow_conf=conf(8),
                    wrist_id_h0=geo0["wrist_id"],
                    face_height=r["face_height"],
                    mouth=json.dumps(r["mouth"]),
                    hand=json.dumps(geo["hand"]),
                    crop_center=json.dumps(geo["crop"]["center"]),
                    crop_side=geo["crop"]["side"],
                    padding_ltrb=json.dumps(padding),
                    source=json.dumps(r["source"]),
                )
                rows.append(row)
                after[(*key, "loose")] += 1
                after[(*key, "tight")] += tight
                if label == "empty_hand":
                    neg_after[(*negkey, "loose")] += 1
                    neg_after[(*negkey, "tight")] += tight
                if time.monotonic() - last_log >= 60:
                    log(
                        f"Loose crop build {job_index}/{len(inputs)} clips: "
                        f"{len(rows)} crops retained"
                    )
                    last_log = time.monotonic()
        finally:
            for cap in caps.values():
                cap.release()
        log(f"Finished loose crops {ds} {job['clip']}: {len(rows)} total retained")
    write_csv(run / "manifest.csv", rows)
    balance = []
    pairs = sorted({(ds, sp) for (ds, _), sp in assignments.items() if sp in ("train", "val")})
    for ds, sp in pairs:
        for cls in ("cup_bottle", "food", "empty_hand"):
            key = (cls, ds, sp)
            balance.append(
                dict(
                    target=cls,
                    dataset=ds,
                    split=sp,
                    loose_before=before[(*key, "loose")],
                    tight_before=before[(*key, "tight")],
                    loose=after[(*key, "loose")],
                    tight=after[(*key, "tight")],
                    loose_only=after[(*key, "loose")] - after[(*key, "tight")],
                )
            )
    write_csv(run / "balance.csv", balance)
    negative = []
    for ds, sp, label in sorted({key[:3] for key in neg_before}):
        key = (ds, sp, label)
        negative.append(
            dict(
                dataset=ds,
                split=sp,
                original_label=label,
                loose_before=neg_before[(*key, "loose")],
                tight_before=neg_before[(*key, "tight")],
                loose=neg_after[(*key, "loose")],
                tight=neg_after[(*key, "tight")],
            )
        )
    write_csv(run / "empty_hand_breakdown.csv", negative)
    coverage = make_class_sheets(run, rows)
    result = dict(
        h=H,
        K=K,
        min_gap_s=MIN_GAP,
        seed=27,
        count=len(rows),
        before_thinning=sum(v for key, v in before.items() if key[-1] == "loose"),
        after_thinning=len(rows),
        tight_retained=sum(r["tight"] for r in rows),
        excluded_test_records=excluded_test,
        excluded_h0_tight_outside_loose=excluded_tight_not_loose,
        tight_definition="dist_h0<=1 within thinned loose corpus; same stored h=.35 crops",
        crop="midpoint of mouth/hand; side=max(2FH,1.3*distance); replicate padding at image edge",
        normalization="128px gray; AREA resize; D9 per-crop 1-99 percentile stretch",
        sheets=coverage,
        inference_calls=0,
        training=False,
    )
    (run / "build.json").write_text(json.dumps(result, indent=2), encoding="utf8")
    saved = json.loads((run / "build.json").read_text(encoding="utf8"))
    log(
        "Read build.json counts: "
        + json.dumps(
            {
                k: saved[k]
                for k in (
                    "before_thinning",
                    "after_thinning",
                    "tight_retained",
                    "excluded_test_records",
                    "excluded_h0_tight_outside_loose",
                )
            }
        )
    )
    for filename in ("balance.csv", "empty_hand_breakdown.csv"):
        with open(run / filename, encoding="utf8") as f:
            for row in csv.DictReader(f):
                log("Read " + filename + ": " + json.dumps(row))
    for key, status in saved["sheets"].items():
        log("Read sheet coverage " + key + ": " + json.dumps(status))
    log("Loose held-object crop build complete; classifier training has not started")


if __name__ == "__main__":
    main()
