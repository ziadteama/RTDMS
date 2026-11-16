"""Phase A wrist audit; no training or deployed-rule changes.

Run with the existing rtdms-train Python: held_wrist.py [--sets syndd,3mdad,ebdd,dad].
Outputs, including per-clip geometry, stay in ../_held_data/.
The first attempt was sandbox-blocked; the resumed run is documented in HELD_OBJECT.md.
"""
# ruff: noqa: E402
import argparse
import csv
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
OUT = BASE / "_held_data"
DATA = Path("D:/rtdms-data")
sys.path.insert(0, str(BASE.parent / "src"))
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OPENCV_FFMPEG_THREADS", "1")

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
VERSION = 2
_POSE = None


def log(message):
    line = f"[{datetime.now():%H:%M}] Codex: {message}"
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "LIVE.log", "a", encoding="utf8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def pose_points(gray, lm):
    global _POSE
    if _POSE is None:
        weights = BASE.parent / "models/yolo26n_pose_320_ncnn_model"
        _POSE = PoseEstimator(PoseConfig(weights=str(weights)))
    person = driver_person(_POSE.detect(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)),
                           None if lm is None else (lm[10] + lm[152]) / 2)
    return person.kpts if person else np.zeros((17, 3))


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
        cap = cv2.VideoCapture(str(src), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, round(fps / 10))
        total = round(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        indices = set()
        for start, end, label, cls in job["segments"]:
            if target(label, cls):
                first = max(0, int(np.ceil(start * fps / step)) * step)
                stop = min(total, int(end * fps) + 1) if np.isfinite(end) else total
                indices.update(range(first, stop, step))
        for i in sorted(indices):
            current = round(cap.get(cv2.CAP_PROP_POS_FRAMES))
            delta = i - current
            if 0 <= delta <= 90:
                for _ in range(delta):
                    cap.grab()
            else:
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, fr = cap.read()
            if not ok:
                raise OSError(f"Cannot decode {src} frame {i}")
            yield i / fps, cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), dict(video=str(src), frame=i)
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
                    poses = z["kp"] if "kp" in z.files else None
                    return kind, {round(float(t), 1): (bool(ok), lm.copy(),
                        poses[i].copy() if poses is not None else None)
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


def cached_frames(job, cache, parity_times):
    """Rich-cache geometry needs no video decode except the NCNN agreement samples."""
    cap = cv2.VideoCapture(job["src"], cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = round(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    shape_only = np.empty((height, width), np.uint8)
    for t in sorted(cache):
        i = round(t * fps)
        gray = shape_only
        if t in parity_times:
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, bgr = cap.read()
            if not ok:
                raise OSError(f"Cannot decode agreement frame {job['src']}:{i}")
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        yield t, gray, dict(video=job["src"], frame=i)
    cap.release()


def audit_job(job):
    cv2.setNumThreads(1)
    ds = job["dataset"]
    dest = OUT / "geometry" / f"{ds}_{job['clip']}.json"
    if dest.exists():
        data = json.loads(dest.read_text(encoding="utf8"))
        reuse = data.get("version") == VERSION and data["job"] == job
        if ds == "syndd" and any(r["face_source"] == "new_mesh" for r in data["records"]):
            reuse = False  # Reuse existing face cache after the timestamp-grid correction.
        if ds == "syndd" and job["split"] == "val":
            reuse = reuse and len({r["t"] for r in data["parity"]}) == 10
        if reuse:
            log(f"Resume audit {ds} {job['clip']}: {len(data['records'])} cached frames")
            return str(dest)
    kind, cache = load_cache(job)
    records, parity = [], []
    parity_times = set()
    if ds == "syndd" and job["split"] == "val" and kind == "rich":
        valid = [t for t, (ok, lm, kp) in cache.items() if ok and kp is not None
                 and any(k[2] >= CONF for k in kp[9:11])]
        parity_times = set(random.Random(job["clip"]).sample(valid, min(10, len(valid))))
    last_log = time.monotonic()
    stream = cached_frames(job, cache, parity_times) if kind == "rich" else frames(job)
    for t, gray, source in stream:
        if gray is None:
            raise OSError(f"Cannot decode {source}")
        key = round(t, 1) if ds == "syndd" else round(t, 3)
        seg = next((s for s in job["segments"] if s[0] <= t <= s[1]
                    and target(s[2], s[3])), None)
        parity_sample = key in parity_times
        if seg is None and not parity_sample:
            continue
        # Match the release's plain whole-frame 640-wide view (aspect preserved).
        raw_h, raw_w = gray.shape
        scale = raw_w / 640.0
        view = None
        if kind != "rich" or parity_sample:
            view = cv2.resize(gray, (640, round(raw_h / scale)), interpolation=cv2.INTER_AREA)
        entry = cache.get(key)
        lm, kp = None, None
        if entry is not None:
            ok, lm, kp = entry
            lm = lm.copy() if ok else None
            kp = kp.copy() if kp is not None else None
        else:
            lm = extract.faces()(view, upscale=2.0 if ds == "dad" else 1.0)
        if parity_sample and lm is not None and kp is not None:
            ncnn_kp = pose_points(view, lm)
            fh = float(np.linalg.norm(lm[10] - lm[152]))
            for wrist in (9, 10):
                if kp[wrist, 2] >= CONF:
                    both = bool(np.isfinite(ncnn_kp[wrist]).all()
                                and ncnn_kp[wrist, 2] >= CONF)
                    error = float(np.linalg.norm(kp[wrist, :2]-ncnn_kp[wrist, :2])/fh)
                    parity.append(dict(t=t, wrist=wrist, cached_conf=float(kp[wrist, 2]),
                                       ncnn_conf=float(ncnn_kp[wrist, 2]), both=both,
                                       error=error if both else None))
        if seg is None:
            continue
        if kp is None:
            kp = pose_points(view, lm)
            pose_source = "ncnn"
        else:
            pose_source = "rich_pytorch"
        # Store all final geometry in original-frame pixels for A2.
        if lm is not None:
            lm = lm * scale
        kp = kp.copy()
        kp[:, :2] *= scale
        label, cls = seg[2:]
        geo = geometry(lm, kp)
        r = dict(t=t, label=label, cls=cls, target=target(label, cls), source=source,
                 kp=kp.tolist(), pose_source=pose_source,
                 lm7=None if lm is None else lm[[1, 10, 13, 14, 152, 234, 454]].tolist(),
                 face_source=kind if entry is not None else "new_mesh", **geo)
        records.append(r)
        if time.monotonic() - last_log >= 60:
            log(f"Pose {ds} {job['clip']}: {len(records)} selected frames processed, t={t:.1f}s")
            last_log = time.monotonic()
    payload = dict(version=VERSION, job=job, records=records, parity=parity)
    dest.write_text(json.dumps(payload), encoding="utf8")
    # Explicit reusable local pose/face cache; no writes to the source data volume.
    np.savez_compressed(OUT / "pose_face" / f"{ds}_{job['clip']}.npz",
                        t=np.array([r["t"] for r in records]),
                        kp=np.array([r["kp"] for r in records], np.float32),
                        lm7=np.array([r["lm7"] if r["lm7"] else [[float("nan")]*2]*7
                                      for r in records], np.float32))
    log(f"Finished pose {ds} {job['clip']}: {len(records)} frames; existing face source={kind}")
    return str(dest)


def read_frame(source, caps):
    if "image" in source:
        return cv2.imread(source["image"], 0)
    if source["video"] not in caps:
        caps[source["video"]] = cv2.VideoCapture(
            source["video"], cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    cap = caps[source["video"]]
    cap.set(cv2.CAP_PROP_POS_FRAMES, source["frame"])
    ok, bgr = cap.read()
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if ok else None


def make_wrist_sheets(paths):
    samples = defaultdict(list)
    rng = random.Random(23)
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf8"))
        job = data["job"]
        # Keep a bounded random pool, stratified by weak target and proximity.
        groups = defaultdict(list)
        for r in data["records"]:
            groups[r["target"]].append(r)
        for label, records in groups.items():
            for r in rng.sample(records, min(16, len(records))):
                samples[(job["dataset"], label)].append((job, r))
    for ds in sorted({k[0] for k in samples}):
        selected = []
        for label in ("cup_bottle", "food", "empty_hand"):
            pool = samples[(ds, label)]
            selected += rng.sample(pool, min(16, len(pool)))
        tiles, index, caps = [], [], {}
        for job, r in selected:
            gray = read_frame(r["source"], caps)
            if gray is None:
                raise OSError(r["source"])
            view = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            if r["face"]:
                mouth = tuple(np.rint(r["mouth"]).astype(int))
                cv2.circle(view, mouth, round(r["face_height"]), (255, 180, 0), 2)
                cv2.circle(view, mouth, 4, (0, 0, 255), -1)
            for w in r["kp"][9:11]:
                if np.isfinite(w).all() and w[2] >= CONF:
                    cv2.circle(view, tuple(np.rint(w[:2]).astype(int)), 4, (0, 255, 0), -1)
            h = min(150, round(view.shape[0] * 256 / view.shape[1]))
            tile = np.zeros((176, 256, 3), np.uint8)
            tile[:h] = cv2.resize(view, (256, h))
            cv2.putText(tile, f"{job['clip']} {r['t']:.1f}"[:38], (2, 162),
                        cv2.FONT_HERSHEY_SIMPLEX, .32, (255, 255, 255), 1)
            cv2.putText(tile, f"{job['split']} {r['label']}", (2, 173),
                        cv2.FONT_HERSHEY_SIMPLEX, .3, (255, 255, 255), 1)
            tiles.append(tile)
            index.append(dict(clip=job["clip"], split=job["split"], record=r))
        for cap in caps.values():
            cap.release()
        sheet(tiles, OUT / "sheets" / f"wrist_{ds}.jpg")
        (OUT / "sheets" / f"wrist_{ds}.json").write_text(json.dumps(index), encoding="utf8")
        log(f"Wrist contact sheet written: sheets/wrist_{ds}.jpg ({len(tiles)} distinct frames)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="syndd,3mdad,ebdd,dad")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    for folder in (OUT, OUT / "geometry", OUT / "pose_face", OUT / "sheets"):
        folder.mkdir(parents=True, exist_ok=True)
    (OUT / "audit_complete.json").unlink(missing_ok=True)
    tasks = [job for ds in args.sets.split(",") for job in jobs(ds)]
    log(f"Starting four-set wrist audit: {len(tasks)} jobs, "
        f"{args.workers} CPU workers; NCNN at 320")
    paths = []
    with ProcessPoolExecutor(args.workers) as pool:
        for path in pool.map(audit_job, tasks):
            paths.append(path)
            if len(paths) % 10 == 0:
                log(f"Audit progress: {len(paths)}/{len(tasks)} clips/videos complete")
    summary = defaultdict(lambda: defaultdict(int))
    parity = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf8"))
        job = data["job"]
        for r in data["records"]:
            c = summary[(job["dataset"], job["split"], r["cls"])]
            c["frames"] += 1
            c["face_frames"] += int(r["face"])
            c["wrist_frames"] += int(r["wrist"])
            c["pair_frames"] += int(r["distance"] is not None)
            for k in KS:
                c[f"near_{k}"] += int(r["distance"] is not None and r["distance"] <= k)
        parity += [dict(clip=job["clip"], **r) for r in data["parity"]]
    rows = [dict(dataset=ds, split=sp, cls=cls, **counts)
            for (ds, sp, cls), counts in sorted(summary.items())]
    with open(OUT / "wrist_summary.csv", "w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    errors = [r["error"] for r in parity if r["both"]]
    result = dict(frames=len({(r["clip"], r["t"]) for r in parity}),
                  cached_usable_wrists=len(parity), both_usable_wrists=len(errors),
                  mean_face_heights=float(np.mean(errors)),
                  within_025_percent=100*sum(e <= .25 for e in errors)/len(errors),
                  rows=parity)
    agreement_path = OUT / "syndd_val_ncnn_agreement.json"
    agreement_path.write_text(json.dumps(result, indent=2), encoding="utf8")
    # Log results only after reading the actual files back.
    saved = json.loads((OUT / "syndd_val_ncnn_agreement.json").read_text())
    log(f"Read agreement file: {saved['frames']} val frames, "
        f"{saved['both_usable_wrists']}/{saved['cached_usable_wrists']} paired wrists, "
        f"mean={saved['mean_face_heights']:.4f} face heights, "
        f"within .25={saved['within_025_percent']:.2f}%")
    with open(OUT / "wrist_summary.csv", encoding="utf8") as f:
        for r in csv.DictReader(f):
            if r["cls"] in ("drinking", "eating", "normal"):
                log(f"Read wrist_summary.csv: {r['dataset']} {r['split']} {r['cls']}: "
                    f"frames={r['frames']}, usable wrist={r['wrist_frames']}, "
                    f"near K=.75/1/1.5={r['near_0.75']}/{r['near_1.0']}/{r['near_1.5']}")
    log("Starting dataset wrist contact sheets with mouth, confident wrists and K=1 circle")
    make_wrist_sheets(paths)
    (OUT / "audit_complete.json").write_text(json.dumps(
        dict(version=VERSION, datasets=args.sets.split(","),
             geometry=[str(Path(p).relative_to(OUT)) for p in paths]), indent=2), encoding="utf8")
    log("Four-set wrist audit completed; completion manifest saved. No training performed.")


if __name__ == "__main__":
    main()
