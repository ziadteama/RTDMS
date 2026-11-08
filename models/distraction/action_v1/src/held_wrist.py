"""Phase A wrist audit; no training or deployed-rule changes.

Run with the existing rtdms-train Python: held_wrist.py [--sets syndd,3mdad,ebdd,dad].
Outputs, including per-clip geometry, stay in ../_held_data/.
This script has NOT been executed in the restricted sandbox; see HELD_OBJECT.md.
"""
# ruff: noqa: E402
import argparse
import csv
import json
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
OUT = BASE / "_held_data"
DATA = Path("D:/rtdms-data")
sys.path.insert(0, str(BASE.parent / "src"))
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import cv2
import extract
import numpy as np

# extract.py inserts its historical checkout on sys.path; restore this worktree first.
sys.path.insert(0, str(BASE.parent / "src"))

from rtdms_distraction.config import PoseConfig, SimpleRulesConfig
from rtdms_distraction.pose import PoseEstimator, driver_person

# extract.py's historical absolute checkout path must not select another worktree's task.
extract.FACE_TASK = BASE.parents[1] / "face/models/face_landmarker.task"
CONF = SimpleRulesConfig().texting_kp_conf
KS = (0.75, 1.0, 1.5)
VERSION = 1


def target(label, cls):
    if cls == "drinking":
        return "cup_bottle"
    if cls == "eating":
        return "food"
    # Do not turn the broad "other" class (radio, reaching, makeup, etc.) into negatives.
    if cls in ("normal", "hand_on_face") or label in (
        "neg_talking", "neg_singing", "neg_yawning", "neg_hand_on_head",
        "AC10", "AC11", "AC16", "talking_with_passenger",
    ):
        return "empty_hand"
    return None


def jobs(ds):
    """Use existing CSV driver assignments; fail on inconsistent or absent splits."""
    with open(DATA / f"action_v1/data/v2/{ds}.csv", encoding="utf8") as f:
        rows = list(csv.DictReader(f))
    splits = defaultdict(set)
    for r in rows:
        splits[r["driver"]].add(r["split"])
    if any(len(s) != 1 for s in splits.values()):
        raise ValueError("Driver crosses splits")
    splits = {d: next(iter(s)) for d, s in splits.items()}
    if ds == "syndd":
        from rtdms_distraction.datasets import syndd

        groups = defaultdict(list)
        for s in syndd(DATA / "public/syndd/A1"):
            if s.label in extract.SYNDD_MAP:
                groups[str(s.video)].append(s)
        for src, segs in groups.items():
            driver = segs[0].driver
            yield dict(dataset=ds, clip=Path(src).stem, src=src, driver=driver,
                       split=splits[driver], segments=[
                           [s.start_s + .5, s.end_s - .5, s.label, extract.SYNDD_MAP[s.label]]
                           for s in segs])
        return
    _, sources = extract.jobs(ds)
    sp = json.loads((BASE / "splits/3mdad.json").read_text())
    for src in sources:
        p = Path(src)
        if ds == "3mdad":
            s, a = int(p.parent.name[1:]), int(p.name[2:])
            driver, label, cls = f"3mdad_s{s}", f"AC{a}", extract.MDAD_MAP[a]
            clip = f"S{s}_AC{a}"
            if splits[driver] != ("test" if s in sp["test"] else "train"):
                raise ValueError(f"3MDAD split mismatch: {driver}")
        elif ds == "dad":
            tester, label = p.parent.parent.name, p.parent.name
            driver, clip = f"dad_{tester.lower()}", f"{tester}_{label}"
            cls = "normal" if label.startswith("normal") else extract.DAD_MAP[label][0]
        else:
            stem = re.sub(r"\s+", "", p.stem).upper()
            label = next(k for k in extract.EBDD_MAP if stem.endswith("_" + k))
            driver = "ebdd_" + stem[:-len(label)-1].lower()
            cls, clip = extract.EBDD_MAP[label], f"{driver}_{label}"
        if target(label, cls):
            yield dict(dataset=ds, clip=clip, src=src, driver=driver, split=splits[driver],
                       segments=[[.5, float("inf"), label, cls]])


def frames(job):
    """SynDD 10 fps; 3MDAD every stored image (~3 fps); DAD every 4th image;
    EBDD every 3rd video frame. Preserve the release's assumed 3MDAD timestamps.
    """
    ds, src = job["dataset"], Path(job["src"])
    if ds == "3mdad":
        paths = sorted(src.glob("*.jpg"), key=lambda p: int(re.search(r"F(\d+)", p.stem)[1]))
        for i, p in enumerate(paths):
            yield i / 3, cv2.imread(str(p), 0), dict(image=str(p))
    elif ds == "dad":
        paths = sorted(src.glob("img_*.png"), key=lambda p: int(p.stem.split("_")[1]))
        for p in paths[::4]:
            yield int(p.stem.split("_")[1]) / 45, cv2.imread(str(p), 0), dict(image=str(p))
    else:
        cap = cv2.VideoCapture(str(src))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, round(fps / 10))
        i = 0
        while True:
            if i % step:
                if not cap.grab():
                    break
            else:
                ok, bgr = cap.read()
                if not ok:
                    break
                yield i / fps, cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), dict(video=str(src), frame=i)
            i += 1
        cap.release()


def geometry(lm, kp):
    wrists = [k[:2] for k in kp[9:11] if np.isfinite(k).all() and k[2] >= CONF]
    if lm is None:
        return dict(wrist=bool(wrists), face=False, distance=None)
    mouth = (lm[13] + lm[14]) / 2
    fh = float(np.linalg.norm(lm[10] - lm[152]))
    if not np.isfinite([*mouth, fh]).all() or fh <= 1:
        return dict(wrist=bool(wrists), face=False, distance=None)
    distances = [float(np.linalg.norm(w - mouth) / fh) for w in wrists]
    w = wrists[int(np.argmin(distances))] if wrists else None
    return dict(wrist=bool(wrists), face=True, mouth=mouth.tolist(), face_height=fh,
                nearest_wrist=None if w is None else w.tolist(),
                distance=min(distances) if distances else None)


def load_cache(job):
    if job["dataset"] == "syndd":
        # Match names exactly (Rear_view and Rearview are distinct source naming conventions).
        for kind in ("rich", "faces"):
            p = DATA / f"eval_cache/{kind}/fps10/{job['clip']}.npz"
            if p.exists():
                with np.load(p) as z:
                    return kind, {round(float(t), 3): (bool(ok), lm.copy(),
                        z["kp"][i].copy() if "kp" in z else None)
                        for i, (t, ok, lm) in enumerate(zip(z["t"], z["ok"], z["lm"], strict=True))}
        return "missing", {}
    p = DATA / f"action_v1/runs/release_v2/{job['dataset']}/{job['clip']}.json"
    if not p.exists():
        return "missing", {}
    data = json.loads(p.read_text(encoding="utf8"))
    cache = {}
    for r in data["frames"]:
        lm = np.zeros((478, 2), np.float64)
        for k, v in (r["lm"] or {}).items():
            lm[int(k)] = v
        cache[round(r["t"], 3)] = (r["lm"] is not None, lm, None)
    return "release", cache


def sheet(tiles, path):
    if not tiles:
        return
    canvas = np.zeros((6 * 176, 8 * 256, 3), np.uint8)
    for i, tile in enumerate(tiles[:48]):
        y, x = divmod(i, 8)
        canvas[y*176:(y+1)*176, x*256:(x+1)*256] = tile
    cv2.imwrite(str(path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 75])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="syndd,3mdad,ebdd,dad")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "geometry").mkdir(exist_ok=True)
    (OUT / "sheets").mkdir(exist_ok=True)
    (OUT / "audit_complete.json").unlink(missing_ok=True)
    pose = None
    summary = defaultdict(lambda: defaultdict(int))
    rng = random.Random(23)
    completed = []
    for ds in args.sets.split(","):
        tiles, seen = defaultdict(list), defaultdict(int)
        for job in jobs(ds):
            kind, cache = load_cache(job)
            dest = OUT / "geometry" / f"{ds}_{job['clip']}.json"
            records = []
            # Recompute on rerun: avoids silently trusting stale cache parameters.
            for t, gray, source in frames(job):
                if gray is None:
                    raise OSError(f"Cannot decode {source}")
                seg = next((s for s in job["segments"] if s[0] <= t <= s[1]
                            and target(s[2], s[3])), None)
                if seg is None:
                    continue
                label, cls = seg[2:]
                # 10-fps SynDD cache timestamps vs original 30-fps frame rounding.
                key = round(t, 1) if ds == "syndd" else round(t, 3)
                entry = cache.get(key)
                lm, kp = None, None
                if entry is not None:
                    ok, lm, kp = entry
                    lm = lm.copy() if ok else None
                    if lm is not None and ds == "syndd":
                        lm *= gray.shape[1] / 640.0
                    if kp is not None and ds == "syndd":
                        kp = kp.copy()
                        kp[:, :2] *= gray.shape[1] / 640.0
                else:
                    lm = extract.faces()(gray, upscale=2.0 if ds == "dad" else 1.0)
                if kp is None:
                    if pose is None:
                        weights = BASE.parent / "models/yolo26n_pose_320_ncnn_model"
                        cfg = PoseConfig(weights=str(weights))
                        pose = PoseEstimator(cfg)
                    person = driver_person(pose.detect(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)),
                                           None if lm is None else (lm[10] + lm[152]) / 2)
                    kp = person.kpts if person else np.zeros((17, 3))
                geo = geometry(lm, kp)
                r = dict(t=t, label=label, cls=cls, target=target(label, cls), source=source,
                         kp=kp.tolist(),
                         face_source=kind if entry is not None else "new_mesh", **geo)
                records.append(r)
                counts = summary[(ds, job["split"], cls)]
                counts["frames"] += 1
                counts["face_frames"] += geo["face"]
                counts["wrist_frames"] += geo["wrist"]
                counts["pair_frames"] += geo["distance"] is not None
                for k in KS:
                    counts[f"near_{k}"] += geo["distance"] is not None and geo["distance"] <= k
                group = r["target"]
                seen[group] += 1
                group_tiles = tiles[group]
                slot = len(group_tiles) if len(group_tiles) < 16 else rng.randrange(seen[group])
                if slot < 16:
                    view = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                    scale = 256 / view.shape[1]
                    if geo["face"]:
                        mouth = tuple(np.rint(geo["mouth"]).astype(int))
                        cv2.circle(view, mouth, 4, (0, 0, 255), -1)
                    for w in kp[9:11]:
                        if w[2] >= CONF:
                            cv2.circle(view, tuple(np.rint(w[:2]).astype(int)), 4, (0, 255, 0), -1)
                    view = cv2.resize(view, (256, max(1, round(view.shape[0]*scale))))
                    tile = np.zeros((176, 256, 3), np.uint8)
                    height = min(150, view.shape[0])
                    tile[:height] = cv2.resize(view, (256, height))
                    cv2.putText(tile, f"{job['clip']} {t:.1f}"[:38], (2, 166),
                                cv2.FONT_HERSHEY_SIMPLEX, .32, (255, 255, 255), 1)
                    if slot == len(group_tiles):
                        group_tiles.append(tile)
                    else:
                        group_tiles[slot] = tile
            # JSON metadata, no object boxes and no test images in the crop set.
            payload = dict(version=VERSION, job=job, records=records)
            dest.write_text(json.dumps(payload), encoding="utf8")
            completed.append(str(dest.relative_to(OUT)))
            print(ds, job["clip"], len(records), flush=True)
        sampled = [tile for label in ("cup_bottle", "food", "empty_hand") for tile in tiles[label]]
        sheet(sampled, OUT / "sheets" / f"wrist_{ds}.jpg")
    rows = [dict(dataset=ds, split=sp, cls=cls, **counts)
            for (ds, sp, cls), counts in sorted(summary.items())]
    if rows:
        with open(OUT / "wrist_summary.csv", "w", newline="", encoding="utf8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (OUT / "audit_complete.json").write_text(json.dumps(
        dict(version=VERSION, datasets=args.sets.split(","), geometry=completed), indent=2),
        encoding="utf8")


if __name__ == "__main__":
    main()
