"""Idea D: pseudo-label SynDD A2 (15 drivers, no annotations) with the teacher + a temporal
consistency check. Output: <data root>/det_v2/syndd_a2/{images,labels}/train + meta.csv.
A box is kept if conf >= 0.5 and a same-class box with IoU >= 0.3 appears in >= 2 of the 4
neighbouring samples (+-1 s); frames with only rejected boxes are skipped; frames where the
teacher sees nothing (>= 0.15) become background (1 in 3)."""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import csv
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np


OUT = Path(f"{DATA}/det_v2/syndd_a2")
EVERY = 0.5


def one(video: str) -> list:
    import label_video_boxes as L

    m = L._models()
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(EVERY * fps))
    samples, i = [], 0
    while True:
        if i % step:
            if not cap.grab():
                break
            i += 1
            continue
        ok, f = cap.read()
        if not ok:
            break
        t = i / fps
        i += 1
        crop, head = L.driver_crop(f, m["person"])
        if crop is None:
            samples.append((t, None, []))
            continue
        face = L.face_geom(f[crop[1]:crop[3], crop[0]:crop[2]], m)
        if face is not None:
            for k in ("center", "mouth"):
                face[k] = face[k] + np.array(crop[:2])
            face["eye_y"] += crop[1]
            face["chin_y"] += crop[1]
        else:
            face = head
        boxes = L.teacher_boxes(f, crop, m, False, face, L.PHONE)
        h, w = f.shape[:2]
        s = 960 / max(h, w)
        samples.append((t, cv2.resize(f, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA),
                        [(b[0], b[1], b[2] / w, b[3] / h, b[4] / w, b[5] / h) for b in boxes]))
    cap.release()

    def iou(a, b):
        ix = max(0.0, min(a[4], b[4]) - max(a[2], b[2]))
        iy = max(0.0, min(a[5], b[5]) - max(a[3], b[3]))
        inter = ix * iy
        u = (a[4] - a[2]) * (a[5] - a[3]) + (b[4] - b[2]) * (b[5] - b[3]) - inter
        return inter / u if u > 0 else 0.0

    rows = []
    stem0 = Path(video).stem
    drv = Path(video).parent.name
    for j, (t, img, boxes) in enumerate(samples):
        if img is None:
            continue
        nb = [samples[q][2] for q in (j - 2, j - 1, j + 1, j + 2) if 0 <= q < len(samples)]
        keep = [b for b in boxes if b[1] >= 0.5 and
                sum(any(o[0] == b[0] and iou(o, b) >= 0.3 for o in n) for n in nb) >= 2]
        weak = [b for b in boxes if b[1] >= 0.15 and b not in keep]
        phones = [b for b in keep if b[0] == 0]
        keep = ([max(phones, key=lambda b: b[1])] if phones else []) + [b for b in keep if b[0] != 0]
        if keep and not [b for b in weak if b[0] == 0 and b[1] >= 0.5]:
            kind = "positive"
        elif not boxes or max(b[1] for b in boxes) < 0.15:
            if j % 3:
                continue
            kind, keep = "background", []
        else:
            continue
        stem = f"syndd_a2__{drv}__{stem0}_{int(t * 1000):07d}"
        cv2.imwrite(str(OUT / "images" / "train" / f"{stem}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        (OUT / "labels" / "train" / f"{stem}.txt").write_text(
            "".join(f"{b[0]} {(b[2] + b[4]) / 2:.6f} {(b[3] + b[5]) / 2:.6f} {b[4] - b[2]:.6f} "
                    f"{b[5] - b[3]:.6f}\n" for b in keep), encoding="utf8")
        rows.append({"split": "train", "source": "syndd_a2", "driver": drv, "label": kind,
                     "image": f"train/{stem}.jpg", "boxes": ";".join(str(b[0]) for b in keep)})
    return rows


if __name__ == "__main__":
    (OUT / "images" / "train").mkdir(parents=True, exist_ok=True)
    (OUT / "labels" / "train").mkdir(parents=True, exist_ok=True)
    videos = sorted(str(p) for p in Path(f"{DATA}/public/syndd/A2").rglob("*.MP4"))
    rows = []
    with ProcessPoolExecutor(2) as ex:
        for r in ex.map(one, videos):
            rows += r
            print(len(rows), "frames so far", flush=True)
    with open(OUT / "meta.csv", "w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(Counter(r["label"] for r in rows), Counter(r["boxes"] for r in rows).most_common(5))
