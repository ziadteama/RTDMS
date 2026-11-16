"""Verify loose Phase A crops, manifest gates, thinning, splits and source preservation."""

# ruff: noqa: E402
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
import cv2
from build_held import MIN_GAP, RUN_NAME, candidate
from held_wrist import DATA, OUT, log


def main():
    log("Starting saved loose-corpus verification: all images, both gates, .3s spacing, splits")
    run = OUT / RUN_NAME
    saved = json.loads((run / "build.json").read_text(encoding="utf8"))
    expected = Counter()
    before = 0
    for p in sorted((OUT / "geometry_v2/base").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf8"))
        j = d["job"]
        if j["split"] == "test":
            continue
        last_t = -float("inf")
        for r in sorted(d["records"], key=lambda r: r["t"]):
            found = candidate(r)
            if found is None:
                continue
            before += 1
            if r["t"] - last_t < MIN_GAP - 1e-6:
                continue
            last_t = r["t"]
            expected[(j["dataset"], j["clip"], r["t"], r["target"])] += 1
    with open(run / "manifest.csv", encoding="utf8") as f:
        rows = list(csv.DictReader(f))
    assignments = {}
    for ds in ("syndd", "3mdad", "ebdd", "dad"):
        with open(DATA / f"action_v1/data/v2/{ds}.csv", encoding="utf8") as f:
            for r in csv.DictReader(f):
                key = (ds, r["driver"])
                assert assignments.get(key, r["split"]) == r["split"]
                assignments[key] = r["split"]
    actual, balance, seen, drivers, times = (
        Counter(),
        Counter(),
        set(),
        defaultdict(set),
        defaultdict(list),
    )
    for i, r in enumerate(rows, 1):
        assert r["split"] in ("train", "val")
        assert assignments[(r["dataset"], r["driver"])] == r["split"]
        assert r["split"] != "val" or r["dataset"] == "syndd"
        assert r["face_source"] in ("mesh", "held", "pose-fallback")
        assert float(r["dist_h035"]) <= 1.25
        assert int(r["tight"]) == int(float(r["dist_h0"]) <= 1)
        assert float(r["wrist_conf"]) >= 0.3
        if int(r["elbow_usable"]):
            assert float(r["elbow_conf"]) >= 0.3
        path = OUT / r["path"]
        assert path.resolve().is_relative_to(run.resolve())
        assert r["path"] not in seen
        seen.add(r["path"])
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        assert image is not None and image.shape == (128, 128)
        actual[(r["dataset"], r["clip"], float(r["t"]), r["target"])] += 1
        balance[(r["target"], r["dataset"], r["split"], "loose")] += 1
        balance[(r["target"], r["dataset"], r["split"], "tight")] += int(r["tight"])
        times[(r["dataset"], r["clip"])].append(float(r["t"]))
        drivers[r["split"]].add((r["dataset"], r["driver"]))
        if i % 5000 == 0:
            log(f"Loose-corpus verification: {i}/{len(rows)} images checked")
    assert actual == expected
    assert before == saved["before_thinning"] and len(rows) == saved["after_thinning"]
    for ts in times.values():
        ts = sorted(ts)
        assert all(b - a >= 0.3 - 1e-6 for a, b in zip(ts, ts[1:], strict=False))
    assert not drivers["train"].intersection(drivers["val"])
    assert not (run / "test").exists()
    assert len(list(run.glob("train/*/*.jpg"))) + len(list(run.glob("val/*/*.jpg"))) == len(rows)
    with open(run / "balance.csv", encoding="utf8") as f:
        for r in csv.DictReader(f):
            for subset in ("loose", "tight"):
                assert int(r[subset]) == balance[(r["target"], r["dataset"], r["split"], subset)]
    for key, status in saved["sheets"].items():
        split, label, subset = key.split("/")
        stem = f"sheet_{split}_{label}_{subset}"
        selected = json.loads((run / f"{stem}.json").read_text(encoding="utf8"))
        assert len(selected) == min(48, status["available"])
        assert len({r["path"] for r in selected}) == len(selected)
        assert all(
            r["path"] in seen
            and r["split"] == split
            and r["target"] == label
            and r["subset"] == subset
            for r in selected
        )
        assert cv2.imread(str(run / f"{stem}.jpg")) is not None
    fingerprints = json.loads((OUT / "source_fingerprints.json").read_text(encoding="utf8"))
    for p, sha in fingerprints.items():
        assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha, p
    result = dict(
        passed=True,
        crops_checked=len(rows),
        before_thinning=before,
        minimum_gap_s=0.3,
        unchanged_source_files=len(fingerprints),
        class_sheets=12,
        drivers={k: len(v) for k, v in drivers.items()},
        test_crops=0,
    )
    (run / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf8")
    log(
        "Read verification.json: " + json.dumps(json.loads((run / "verification.json").read_text()))
    )


if __name__ == "__main__":
    main()
