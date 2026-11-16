"""Step 0: open sample frames of every dataset found on D: (read-only) and measure what they are:
resolution, fps (videos), and colour vs grey (mean |R-G| + |G-B| per pixel; ~0 = grey / IR).
Writes _held_data/ir/inventory_probe.json and a contact sheet of one frame per source.

python inventory_probe.py
"""

import json
import random
from pathlib import Path

import cv2
import numpy as np

OUT = Path(__file__).resolve().parent.parent / "_held_data/ir"
OUT.mkdir(parents=True, exist_ok=True)
D = Path("D:/")
SOURCES = {
    "SynDD A1 rear view": (D / "rtdms-data/public/syndd/A1", "Rear*.MP4"),
    "SynDD A1 dashboard": (D / "rtdms-data/public/syndd/A1", "Dash*.MP4"),
    "SynDD A1 right window": (D / "rtdms-data/public/syndd/A1", "Right*.MP4"),
    "SynDD A2": (D / "rtdms-data/public/syndd/A2", "*.MP4"),
    "3MDAD Day-RGB2 front": (D / "rtdms-data/raw/3mdad/front/Day-RGB2", "*.jpg"),
    "DAD front_IR": (D / "rtdms-data/raw/dad/x/DAD", "front_IR/*.png"),
    "DAD top_IR": (D / "rtdms-data/raw/dad/x/DAD", "top_IR/*.png"),
    "EBDD": (D / "rtdms-data/raw/ebdd/x", "*.*4"),
    "Drive&Act inner_mirror": (D / "Data Sets/inner_mirror", "*.mp4"),
    "Drive&Act steering_wheel": (D / "Data Sets/steering_wheel", "*.mp4"),
    "UTA-RLDD Fold3_part2": (D / "Data Sets/Fold3_part2", "*.mp4"),
    "MRL Eye (Data Sets/data)": (D / "Data Sets/data", "*.png"),
    "p022 ir1": (D / "Data Sets/p022", "*_ir1_*"),
    "p022 depth": (D / "Data Sets/p022", "*_depth_*.bmp"),
    "AUC v1 cam1": (D / "Data Sets/v1_cam1_no_split", "*.jpg"),
    "AUC v2 Camera 1": (D / "Data Sets/v2_cam1_cam2_ split_by_driver/Camera 1", "*.jpg"),
    "AUC v2 Camera 2": (D / "Data Sets/v2_cam1_cam2_ split_by_driver/Camera 2", "*.jpg"),
}


def colour(img):
    if img is None:
        return None
    if img.ndim == 2:
        return 0.0
    b, g, r = [img[..., i].astype(np.int16) for i in range(3)]
    return float(np.mean(np.abs(r - g) + np.abs(g - b)))


def sample(root, pattern, n=4):
    files = []
    for i, p in enumerate(root.rglob(pattern)):
        files.append(p)
        if i > 4000:
            break
    random.Random(0).shuffle(files)
    return files[:n]


res, tiles = {}, []
for name, (root, pattern) in SOURCES.items():
    if not root.exists():
        res[name] = "path missing"
        continue
    files = sample(root, pattern)
    if not files:
        res[name] = f"no files matching {pattern}"
        continue
    info = []
    for p in files:
        if p.suffix.lower() in (".mp4", ".avi", ".mov"):
            cap = cv2.VideoCapture(str(p))
            n = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(n // 2))
            ok, img = cap.read()
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
            img = img if ok else None
        else:
            img, fps = cv2.imread(str(p), cv2.IMREAD_UNCHANGED), None
        info.append(dict(file=str(p), shape=None if img is None else list(img.shape),
                         fps=fps, colour=colour(img)))
        if img is not None and len(info) == 1:
            t = img if img.ndim == 3 else cv2.cvtColor(cv2.convertScaleAbs(img, alpha=255.0 / max(1, img.max())) if img.dtype != np.uint8 else img, cv2.COLOR_GRAY2BGR)
            t = cv2.resize(t, (320, int(320 * t.shape[0] / t.shape[1])))
            t = cv2.copyMakeBorder(t, 0, max(0, 240 - t.shape[0]), 0, 0, cv2.BORDER_CONSTANT)[:240]
            cv2.putText(t, name[:38], (4, 16), 0, 0.45, (0, 255, 255), 1)
            tiles.append(t)
    res[name] = info
    cols = [i["colour"] for i in info if i["colour"] is not None]
    print(f"{name}: shape {info[0]['shape']} fps {info[0]['fps']} colour {np.round(cols, 1)}")
(OUT / "inventory_probe.json").write_text(json.dumps(res, indent=1))
rows = [np.hstack(tiles[i:i + 4] + [np.zeros_like(tiles[0])] * (4 - len(tiles[i:i + 4])))
        for i in range(0, len(tiles), 4)]
cv2.imwrite(str(OUT / "inventory_sheet.jpg"), np.vstack(rows))
