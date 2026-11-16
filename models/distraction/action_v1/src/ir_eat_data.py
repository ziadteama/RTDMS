"""IR step 3 data: hand-at-mouth crop SEQUENCES from SynDD rear view (monochrome), all splits,
labelled only by the dataset's own time-stamped action labels (no food-visible labels).

Per video, samples at ~3.3 fps (every 3rd frame of the 10 fps caches):
- train: geometry_v2/base records (full-res coordinates; non-phone classes);
- val / test: the rich pose+mesh cache (640-wide coordinates, every class), mouth = mesh, else the
  mesh <= 1 s old, else the pose fallback (D26) — same as the runtime.
Near = hand point within K = 1.25 face heights (held_runtime). Near frames get a 128 px crop
(same crop as the cup model). Phone sequences for TRAIN come from ir_hardneg.py crops.

python ir_eat_data.py  -> _held_data/ir/eat/<split>/<clip>.npz
"""

import importlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
from held_runtime import K, hand_geometry, pose_mouth, square_cover  # noqa: E402

OUT = HERE.parent / "_held_data"
DEST = OUT / "ir/eat"
RICH = Path("D:/rtdms-data/eval_cache/rich/fps10")
FIT = json.loads((OUT / "geometry_v2/mouth_fit.json").read_text())


def samples_train(clip):
    p = OUT / "geometry_v2/base" / f"syndd_{clip}.json"
    if not p.exists():
        return []
    recs = sorted(json.loads(p.read_text())["records"], key=lambda r: r["t"])
    out = []
    for r in recs[::3]:
        kp = np.asarray(r["kp"], float)
        mouth, fh = (np.asarray(r["mouth"]), r["face_height"]) if r["mouth"] else (None, None)
        out.append((r["t"], kp, mouth, fh))
    return out


def samples_cached(clip, width):
    z = np.load(RICH / f"{clip}.npz")
    scale = width / 640
    out, last = [], None
    for i in range(0, len(z["t"]), 3):
        t, kp = float(z["t"][i]), z["kp"][i].astype(float).copy()
        kp[:, :2] *= scale
        if z["ok"][i]:
            lm = z["lm"][i] * scale
            mouth, fh = (lm[13] + lm[14]) / 2, float(np.linalg.norm(lm[10] - lm[152]))
            last = (t, mouth, fh)
        elif last is not None and t - last[0] <= 1:
            _, mouth, fh = last
        else:
            got = pose_mouth(kp, FIT)
            mouth, fh = got if got is not None else (None, None)
        out.append((t, kp, mouth, fh))
    return out


def run(job, split):
    dest = DEST / split / f"{job['clip']}.npz"
    if dest.exists():
        return
    cap = cv2.VideoCapture(job["src"])
    fps, width = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    samples = samples_train(job["clip"]) if split == "train" else samples_cached(job["clip"], width)
    ts, near, crops, cidx = [], [], [], []
    want = {}
    for i, (t, kp, mouth, fh) in enumerate(samples):
        ok = False
        if mouth is not None and fh and fh > 1:
            d, crop = hand_geometry(kp, np.asarray(mouth), fh)
            if d is not None and d <= K:
                want[round(t * fps)] = (i, crop)
                ok = True
        ts.append(t)
        near.append(ok)
        cidx.append(-1)
    pos = 0
    for f in sorted(want):
        while pos < f:
            cap.grab()
            pos += 1
        ok, frame = cap.read()
        pos += 1
        if not ok:
            continue
        i, (center, side) = want[f]
        cidx[i] = len(crops)
        crops.append(square_cover(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), np.asarray(center), side))
    cap.release()
    dest.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dest, t=np.array(ts), near=np.array(near), crop_index=np.array(cidx),
                        crops=np.array(crops, np.uint8).reshape(-1, 128, 128),
                        driver=job["driver"], clip=job["clip"],
                        intervals=json.dumps(job["intervals"]))


def main():
    b = importlib.import_module("phase_b")
    for split in ("val", "test", "train"):
        jobs = b.windows(split)
        for i, job in enumerate(jobs):
            run(job, split)
            print(f"[eat-data] {split} {i + 1}/{len(jobs)} {job['clip']}", flush=True)
    print("[eat-data] done", flush=True)


if __name__ == "__main__":
    main()
