"""Idea E: copy-paste real IR phone cut-outs next to the ear on phone-free SynDD frames (train
drivers only). Output: <data root>/det_v2/syndd_copypaste/{images,labels}/train + meta.csv.
python copy_paste.py <n>"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import csv
import random
import sys
from pathlib import Path

import cv2
import numpy as np

SRC = Path(f"{DATA}/det_v2/syndd")
OUT = Path(f"{DATA}/det_v2/syndd_copypaste")
PHONE_LABELS = {"phone_right_ear", "phone_left_ear"}
TARGET_LABELS = {"normal", "neg_hand_on_head", "neg_talking", "neg_singing", "neg_yawning"}


def main(n: int) -> int:
    rng = random.Random(0)
    meta = [r for r in csv.DictReader(open(SRC / "meta.csv", encoding="utf8")) if r["split"] == "train"]
    # phone cut-outs (tight boxes only: <= 3 % of the frame, aspect 0.3-1.2)
    cuts = []
    for r in [r for r in meta if r["label"] in PHONE_LABELS][:6000]:
        lab = (SRC / "labels" / r["image"]).with_suffix(".txt").read_text().split("\n")
        for ln in lab:
            p = ln.split()
            if len(p) == 5 and p[0] == "0":
                x, y, w, h = map(float, p[1:])
                if w * h <= 0.03 and 0.3 <= w * 960 / (h * 540) <= 1.2:
                    cuts.append((r["image"], x, y, w, h, r["driver"]))
    rng.shuffle(cuts)
    targets = [r for r in meta if r["label"] in TARGET_LABELS]
    rng.shuffle(targets)
    from ultralytics import YOLO

    pose = YOLO(str(REPO / "models/yolo26n-pose.pt"))
    (OUT / "images" / "train").mkdir(parents=True, exist_ok=True)
    (OUT / "labels" / "train").mkdir(parents=True, exist_ok=True)
    rows, ci = [], 0
    for r in targets:
        if len(rows) >= n:
            break
        img = cv2.imread(str(SRC / "images" / r["image"]))
        if img is None:
            continue
        H, Wd = img.shape[:2]
        # The face mesh misses ~98 % of these small faces in IMAGE mode; pose keypoints
        # (0 nose, 1 / 2 eyes, 3 / 4 ears) of the largest person work.
        pr = pose.predict(img, imgsz=640, conf=0.3, verbose=False)[0]
        if not len(pr.boxes):
            continue
        bb = pr.boxes.xyxy.cpu().numpy()
        kp = pr.keypoints.data[int(np.argmax((bb[:, 2] - bb[:, 0]) * (bb[:, 3] - bb[:, 1])))]
        kp = kp.cpu().numpy()
        ears = [kp[j, :2] for j in (3, 4) if kp[j, 2] >= 0.4]
        if not ears or kp[0, 2] < 0.4:
            continue
        if kp[3, 2] >= 0.4 and kp[4, 2] >= 0.4:
            fw = float(np.linalg.norm(kp[3, :2] - kp[4, :2]))
        elif kp[1, 2] >= 0.4 and kp[2, 2] >= 0.4:
            fw = 2.2 * float(np.linalg.norm(kp[1, :2] - kp[2, :2]))
        else:
            continue
        if fw < 20:
            continue
        # a cut-out from a different driver
        while ci < len(cuts) and cuts[ci][5] == r["driver"]:
            ci += 1
        if ci >= len(cuts):
            ci = 0
            continue
        cimg, cx, cy, cw, ch, _ = cuts[ci]
        ci += 1
        src = cv2.imread(str(SRC / "images" / cimg))
        sh, sw = src.shape[:2]
        x1, y1 = int((cx - cw / 2) * sw), int((cy - ch / 2) * sh)
        x2, y2 = int((cx + cw / 2) * sw), int((cy + ch / 2) * sh)
        patch = src[max(0, y1):y2, max(0, x1):x2]
        if patch.size == 0:
            continue
        # phone height ~0.55-0.8 fw, placed over one ear (234 / 454), slightly forward and down
        ear = ears[rng.randrange(len(ears))]
        centre = kp[0, :2]
        ph = fw * rng.uniform(0.55, 0.8)
        pw = ph * patch.shape[1] / patch.shape[0]
        px = ear[0] + (centre[0] - ear[0]) * rng.uniform(0.0, 0.25) - pw / 2
        py = ear[1] + fw * rng.uniform(-0.1, 0.25) - ph / 2
        X0, Y0, X1, Y1 = int(px), int(py), int(px + pw), int(py + ph)
        if X0 < 0 or Y0 < 0 or X1 > Wd or Y1 > H or X1 - X0 < 6 or Y1 - Y0 < 6:
            continue
        p = cv2.resize(patch, (X1 - X0, Y1 - Y0)).astype(np.float32)
        roi = img[Y0:Y1, X0:X1].astype(np.float32)
        p = (p - p.mean()) / (p.std() + 1e-3) * max(p.std(), 8.0) + 0.5 * (p.mean() + roi.mean())
        mask = np.zeros(p.shape[:2], np.float32)
        cv2.rectangle(mask, (1, 1), (p.shape[1] - 2, p.shape[0] - 2), 1.0, -1)
        k = max(3, (min(p.shape[:2]) // 5) | 1)
        mask = cv2.GaussianBlur(mask, (k, k), 0)[..., None]
        img[Y0:Y1, X0:X1] = np.clip(mask * p + (1 - mask) * roi, 0, 255).astype(np.uint8)
        stem = Path(r["image"]).stem + "__cp"
        cv2.imwrite(str(OUT / "images" / "train" / f"{stem}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        own = (SRC / "labels" / r["image"]).with_suffix(".txt").read_text()
        box = f"0 {(X0 + X1) / 2 / Wd:.6f} {(Y0 + Y1) / 2 / H:.6f} {(X1 - X0) / Wd:.6f} {(Y1 - Y0) / H:.6f}\n"
        (OUT / "labels" / "train" / f"{stem}.txt").write_text(own + box, encoding="utf8")
        rows.append({"split": "train", "source": "syndd_copypaste", "driver": r["driver"],
                     "label": "phone_copypaste", "image": f"train/{stem}.jpg", "boxes": "[0]"})
    with open(OUT / "meta.csv", "w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "copy-paste frames,", len(cuts), "cut-outs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3000))
