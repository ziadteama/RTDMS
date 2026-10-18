"""python frame_val.py <weights> <imgsz> <data yaml> [<data yaml> ...] -> per-class P / R / AP50 / AP50-95"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import json
import sys


def main():
    from ultralytics import YOLO
    w, sz = sys.argv[1], int(sys.argv[2])
    m = YOLO(w)
    out = {}
    for d in sys.argv[3:]:
        r = m.val(data=d, imgsz=sz, batch=16, workers=0, verbose=False, plots=False, split="val")
        b = r.box
        out[d.split("/")[-2]] = {n: {"P": round(float(b.p[i]), 3), "R": round(float(b.r[i]), 3),
                                     "AP50": round(float(b.ap50[i]), 3), "AP": round(float(b.ap[i]), 3)}
                                 for i, n in enumerate(["phone", "drink", "food"]) if i < len(b.p)}
    print("RESULT", json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
