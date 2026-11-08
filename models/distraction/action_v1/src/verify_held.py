"""Validate actual Phase A artifacts, split isolation, images and source fingerprints."""
# ruff: noqa: E402
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True

import cv2
from held_wrist import DATA, OUT, log, target


def main():
    log("Starting Phase A artifact verification: splits, all crop images, sheets, source hashes")
    run = OUT / "crops_k1_side2"
    complete = json.loads((OUT / "audit_complete.json").read_text())
    assert set(complete["datasets"]) == {"syndd", "3mdad", "ebdd", "dad"}
    expected = Counter()
    excluded = 0
    for p in complete["geometry"]:
        data = json.loads((OUT / p).read_text())
        job = data["job"]
        for r in data["records"]:
            assert r["target"] == target(r["label"], r["cls"])
            if job["split"] == "test":
                excluded += 1
            elif r["distance"] is not None and r["distance"] <= 1:
                expected[(r["target"], job["dataset"], job["split"])] += 1
    assignments = {}
    for ds in complete["datasets"]:
        with open(DATA / f"action_v1/data/v2/{ds}.csv", encoding="utf8") as f:
            for r in csv.DictReader(f):
                key = (ds, r["driver"])
                assert assignments.get(key, r["split"]) == r["split"]
                assignments[key] = r["split"]
    with open(run / "manifest.csv", encoding="utf8") as f:
        rows = list(csv.DictReader(f))
    counts, drivers, seen = Counter(), defaultdict(set), set()
    for i, r in enumerate(rows, 1):
        assert r["split"] in ("train", "val")
        assert r["split"] == assignments[(r["dataset"], r["driver"])]
        assert r["split"] != "val" or r["dataset"] == "syndd"
        assert float(r["distance"]) <= 1
        p = OUT / r["path"]
        assert p.resolve().is_relative_to(OUT.resolve())
        assert r["path"] not in seen
        seen.add(r["path"])
        image = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        assert image is not None and image.shape == (128, 128), str(p)
        counts[(r["target"], r["dataset"], r["split"])] += 1
        drivers[r["split"]].add((r["dataset"], r["driver"]))
        if i % 5000 == 0:
            log(f"Artifact verification: {i}/{len(rows)} crop images checked")
    assert counts == expected, (counts, expected)
    assert not drivers["train"].intersection(drivers["val"])
    assert len(list(run.glob("train/*/*.jpg"))) + len(list(run.glob("val/*/*.jpg"))) == len(rows)
    assert not (run / "test").exists()
    for split in ("train", "val"):
        for label in ("cup_bottle", "food", "empty_hand"):
            paths = json.loads((run / f"sheet_{split}_{label}.json").read_text())
            assert len(paths) >= 48 and len(set(paths)) == len(paths)
            for p in paths:
                assert p in seen and f"/{split}/{label}/" in p.replace("\\", "/")
            assert cv2.imread(str(run / f"sheet_{split}_{label}.jpg")) is not None
    for ds in complete["datasets"]:
        assert cv2.imread(str(OUT / "sheets" / f"wrist_{ds}.jpg")) is not None
    fingerprints = json.loads((OUT / "source_fingerprints.json").read_text())
    for p, sha in fingerprints.items():
        assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha, p
    result = dict(passed=True, crops_checked=len(rows), test_records_excluded=excluded,
                  drivers={k: len(v) for k, v in drivers.items()},
                  unchanged_source_files=len(fingerprints), class_sheets=6, wrist_sheets=4)
    (run / "verification.json").write_text(json.dumps(result, indent=2))
    saved = json.loads((run / "verification.json").read_text())
    log("Read verification.json: " + json.dumps(saved))


if __name__ == "__main__":
    main()
