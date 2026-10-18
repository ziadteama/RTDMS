"""Item 1: recover phone boxes the teacher missed inside SynDD phone-call spans with SAM 2 video
tracking, seeded by a teacher box and run forward and backward (train / val drivers only).
python sam_recover.py [limit_clips]
Output: <data root>/det_v2/syndd_sam/{images,labels}/{train,val} (recovered frames only)."""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import csv
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

from rtdms_distraction import datasets as D  # noqa: E402

SRC = Path(f"{DATA}/det_v2/syndd")
OUT = Path(f"{DATA}/det_v2/syndd_sam")
TMP = Path(f"{DATA}/tmp_sam")
EVERY = 0.5
X0 = 0.30  # crop: the driver sits right of 30 % of the frame


def load_known():
    """clip stem -> {ms: (conf, box xyxy normalised)} for phone boxes the labeller kept."""
    known = {}
    for r in csv.DictReader(open(SRC / "meta.csv", encoding="utf8")):
        if r["label"] not in ("phone_right_ear", "phone_left_ear") or r["split"] == "test":
            continue
        m = re.match(r"(.+)_(\d{7})$", Path(r["image"]).stem)
        rows = [list(map(float, ln.split())) for ln in
                (SRC / "labels" / r["image"]).with_suffix(".txt").read_text().splitlines() if ln]
        ph = [b for b in rows if int(b[0]) == 0]
        if m and ph:
            c, x, y, w, h = ph[0]
            known.setdefault(m.group(1), {})[int(m.group(2))] = (x - w / 2, y - h / 2, x + w / 2,
                                                                  y + h / 2)
    return known


def write_clip(frames, path):
    h, w = frames[0].shape[:2]
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 2, (w, h))
    for f in frames:
        vw.write(f)
    vw.release()


def track(pred, frames, seed_xyxy):
    """SAM 2 on a list of BGR crops, box prompt on frame 0 -> list of boxes (crop px) or None."""
    TMP.mkdir(parents=True, exist_ok=True)
    p = TMP / "clip.mp4"
    write_clip(frames, p)
    out = []
    for r in pred(source=str(p), bboxes=[list(map(float, seed_xyxy))], stream=True):
        if r.masks is None or not len(r.boxes):
            out.append(None)
            continue
        out.append(r.boxes.xyxy[0].cpu().numpy())
    return out


def main(limit=None):
    from ultralytics.models.sam import SAM2VideoPredictor

    pred = SAM2VideoPredictor(overrides=dict(conf=0.25, task="segment", mode="predict",
                                             imgsz=1024, model="sam2.1_b.pt", verbose=False))
    split = json.load(open(str(REPO / "configs/syndd_split.json")))
    known = load_known()
    stats = {"clips": 0, "missing": 0, "recovered": 0, "rejected": 0}
    rows = []
    clips = [c for c in D.syndd_clips(f"{DATA}/public/syndd/A1")
             if c.label in ("phone_right_ear", "phone_left_ear") and split.get(c.driver) in
             ("train", "val")]
    for clip in clips[:limit]:
        stem0 = f"{clip.source}__{clip.driver}__{Path(clip.name).stem}"
        kn = known.get(stem0)
        if not kn:
            continue
        samples = list(clip.frames(EVERY))
        if not samples:
            continue
        H, W = samples[0][1].shape[:2]
        x0 = int(X0 * W)
        crops = [f[:, x0:] for _, f in samples]
        times = [int(t * 1000) for t, _ in samples]
        miss = [i for i, ms in enumerate(times) if ms not in kn]
        if not miss:
            continue
        stats["clips"] += 1
        stats["missing"] += len(miss)
        seed_i = min((i for i, ms in enumerate(times) if ms in kn), key=lambda i: i)
        sb = np.array(kn[times[seed_i]]) * [W, H, W, H] - [x0, 0, x0, 0]
        fwd = track(pred, crops[seed_i:], sb)
        bwd = track(pred, crops[: seed_i + 1][::-1], sb)[::-1]
        boxes = bwd[:-1] + fwd  # index-aligned with crops
        s_area = (sb[2] - sb[0]) * (sb[3] - sb[1])
        diag = float(np.hypot(sb[2] - sb[0], sb[3] - sb[1]))
        sp = split[clip.driver]
        for i in miss:
            b = boxes[i] if i < len(boxes) else None
            if b is None:
                stats["rejected"] += 1
                continue
            area = (b[2] - b[0]) * (b[3] - b[1])
            # nearest known box (time) as the reference position
            ref_i = min((j for j, ms in enumerate(times) if ms in kn), key=lambda j: abs(j - i))
            rb = np.array(kn[times[ref_i]]) * [W, H, W, H] - [x0, 0, x0, 0]
            dc = np.hypot((b[0] + b[2] - rb[0] - rb[2]) / 2, (b[1] + b[3] - rb[1] - rb[3]) / 2)
            if not (0.4 * s_area <= area <= 2.5 * s_area) or dc > 2.0 * diag:
                stats["rejected"] += 1
                continue
            stats["recovered"] += 1
            bx = (b + [x0, 0, x0, 0]) / [W, H, W, H]
            f = samples[i][1]
            s = 960 / max(H, W)
            img = cv2.resize(f, (round(W * s), round(H * s)), interpolation=cv2.INTER_AREA)
            stem = f"{stem0}_{times[i]:07d}_sam"
            (OUT / "images" / sp).mkdir(parents=True, exist_ok=True)
            (OUT / "labels" / sp).mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(OUT / "images" / sp / f"{stem}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            (OUT / "labels" / sp / f"{stem}.txt").write_text(
                f"0 {(bx[0] + bx[2]) / 2:.6f} {(bx[1] + bx[3]) / 2:.6f} {bx[2] - bx[0]:.6f} "
                f"{bx[3] - bx[1]:.6f}\n", encoding="utf8")
            rows.append({"split": sp, "source": "syndd", "driver": clip.driver,
                         "label": clip.label, "image": f"{sp}/{stem}.jpg", "boxes": "[0]"})
        if stats["clips"] % 10 == 0:
            print(stats, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if rows:
        with open(OUT / "meta.csv", "w", newline="", encoding="utf8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print("final", stats)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
