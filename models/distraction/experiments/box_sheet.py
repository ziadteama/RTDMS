"""Contact sheet of auto-labelled boxes: python box_sheet.py <dataset dir> <out.jpg> [labels]"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import csv, random, sys
from pathlib import Path
import cv2, numpy as np
root, out = Path(sys.argv[1]), sys.argv[2]
want = sys.argv[3].split(",") if len(sys.argv) > 3 else ["phone_right_ear", "phone_left_ear", "drinking", "eating", "phone_in_hand"]
rows = list(csv.DictReader(open(root / "meta.csv", encoding="utf8")))
COL = {0: (0, 0, 255), 1: (255, 160, 0), 2: (0, 200, 0)}
NAME = {0: "phone", 1: "drink", 2: "food"}
lines = []
for lab in want:
    sel = [r for r in rows if r["label"] == lab]
    random.Random(0).shuffle(sel)
    tiles = []
    for r in sel[:8]:
        img = cv2.imread(str(root / "images" / r["image"]))
        h, w = img.shape[:2]
        txt = (root / "labels" / r["image"]).with_suffix(".txt").read_text().split("\n")
        boxes = [list(map(float, l.split())) for l in txt if l.strip()]
        for c, x, y, bw, bh in boxes:
            cv2.rectangle(img, (int((x - bw / 2) * w), int((y - bh / 2) * h)), (int((x + bw / 2) * w), int((y + bh / 2) * h)), COL[int(c)], 2)
        # zoom on the boxes' area (or the right half where the driver sits)
        if boxes:
            cx = np.mean([b[1] for b in boxes]) * w; cy = np.mean([b[2] for b in boxes]) * h
        else:
            cx, cy = 0.7 * w, 0.5 * h
        s = 170
        x0, y0 = int(np.clip(cx - s, 0, w - 2 * s)), int(np.clip(cy - s, 0, h - 2 * s))
        t = cv2.resize(img[y0:y0 + 2 * s, x0:x0 + 2 * s], (200, 200))
        cv2.putText(t, ",".join(NAME[int(b[0])] for b in boxes)[:22], (3, 195), 0, 0.45, (0, 255, 255), 1)
        tiles.append(t)
    tiles += [np.zeros((200, 200, 3), np.uint8)] * (8 - len(tiles))
    head = np.zeros((200, 150, 3), np.uint8)
    cv2.putText(head, lab, (3, 100), 0, 0.45, (0, 255, 255), 1)
    lines.append(np.hstack([head] + tiles))
cv2.imwrite(out, np.vstack(lines))
