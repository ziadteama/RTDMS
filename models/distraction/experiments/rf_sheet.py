"""Contact sheet for a Roboflow YOLO export: python rf_sheet.py <dir> <out.jpg> [split]"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import random, sys
from pathlib import Path
import cv2, numpy as np, yaml
d, out = Path(sys.argv[1]), sys.argv[2]
split = sys.argv[3] if len(sys.argv) > 3 else "train"
names = yaml.safe_load((d / "data.yaml").read_text())["names"]
names = [names[i] for i in sorted(names)] if isinstance(names, dict) else names
labs = sorted((d / split / "labels").glob("*.txt"))
random.Random(0).shuffle(labs)
rows = []
for ci, cname in enumerate(names):
    tiles = []
    for lp in labs:
        boxes = [list(map(float, l.split()[:5])) for l in lp.read_text().splitlines() if l.strip()]
        if not any(int(b[0]) == ci for b in boxes):
            continue
        ims = [p for p in (d / split / "images").glob(lp.stem + ".*")]
        img = cv2.imread(str(ims[0]))
        h, w = img.shape[:2]
        for c, x, y, bw, bh in boxes:
            col = (0, 0, 255) if int(c) == ci else (120, 120, 120)
            cv2.rectangle(img, (int((x - bw / 2) * w), int((y - bh / 2) * h)), (int((x + bw / 2) * w), int((y + bh / 2) * h)), col, 2)
        tiles.append(cv2.resize(img, (180, 180)))
        if len(tiles) == 8:
            break
    tiles += [np.zeros((180, 180, 3), np.uint8)] * (8 - len(tiles))
    head = np.zeros((180, 120, 3), np.uint8)
    cv2.putText(head, cname, (3, 90), 0, 0.5, (0, 255, 255), 1)
    rows.append(np.hstack([head] + tiles))
cv2.imwrite(out, np.vstack(rows))
img = cv2.imread(str(next((d / split / "images").iterdir())))
print("image size", img.shape)
