"""Per-frame phone detection rate on held-out SynDD drivers (phone segments) and phone false
positives on normal / hand-on-head frames, for each detector."""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2

REPO = REPO
sys.path.insert(0, str(REPO / "src"))
from rtdms_distraction import datasets as D  # noqa: E402
from ultralytics import YOLO  # noqa: E402

split = json.loads((REPO / "configs" / "syndd_split.json").read_text())
test = {d for d, s in split.items() if s == "test"}
POS = {"phone_right_ear", "phone_left_ear", "phone_in_hand"}
NEG = {"normal", "neg_hand_on_head"}
segs = [s for s in D.syndd(f"{DATA}/public/syndd/A1")
        if s.driver in test and s.label in POS | NEG]
frames = []  # (label, frame)
for s in segs:
    cap = cv2.VideoCapture(str(s.video))
    t = s.start_s + 0.5
    while t < s.end_s - 0.5:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, f = cap.read()
        if ok:
            frames.append((s.label, f))
        t += 1.0
    cap.release()
print(len(frames), "frames", {k: sum(1 for x in frames if x[0] == k) for k in POS | NEG},
      flush=True)

DET = {
    **({"det_v2a_416": (Path(sys.argv[2]), 416, 0)} if len(sys.argv) > 2 else {}),
    "stock yolo26n@416": (REPO / "models" / "yolo26n.pt", 416, 67),
    "v1_416": (Path(f"{DATA}/runs/v1_416/weights/best.pt"), 416, 0),
    "v1_512": (Path(f"{DATA}/runs/v1_512/weights/best.pt"), 512, 0),
    "teacher yolo26m@1280 (full frame)": ("yolo26m.pt", 1280, 67),
}
res = {}
for name, (w, sz, cls) in DET.items():
    m = YOLO(str(w))
    hit = defaultdict(int)
    for lab, f in frames:
        r = m.predict(f, imgsz=sz, conf=0.25, classes=[cls], verbose=False)[0]
        hit[lab] += len(r.boxes) > 0
    n = {k: sum(1 for x in frames if x[0] == k) for k in POS | NEG}
    res[name] = {k: round(hit[k] / n[k], 3) for k in n}
    print(name, res[name], flush=True)
json.dump(res, open(sys.argv[1], "w"), indent=1)
