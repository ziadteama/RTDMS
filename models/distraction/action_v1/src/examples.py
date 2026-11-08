"""Report assets: example crops with the model's answer.
- examples_<tag>_<ds>.jpg: per true class, 6 random test crops; caption = predicted class and the
  phone-in-hand probability (max of the two ears). Green-ish frame = right, dark frame = wrong.
- hand_on_face_<tag>.jpg: hand-on-face test crops with their ear crops, the hard case for phones.
python examples.py [tag=v1]
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from alerts import CLASSES  # noqa: E402
from evaluate import PRED, rows  # noqa: E402

A = Path("D:/rtdms-data/action_v1")
OUT = A / "report_assets"


def tile(r, act, ph, ears=False):
    up = cv2.imread(str(A / "data" / r["up"]), cv2.IMREAD_GRAYSCALE)
    im = cv2.cvtColor(up, cv2.COLOR_GRAY2BGR)
    if ears:
        er = cv2.imread(str(A / "data" / r["ear_r"]), cv2.IMREAD_GRAYSCALE)
        el = cv2.imread(str(A / "data" / r["ear_l"]), cv2.IMREAD_GRAYSCALE)
        side = cv2.cvtColor(np.vstack([cv2.resize(er, (112, 112)), cv2.resize(el, (112, 112))]),
                            cv2.COLOR_GRAY2BGR)
        im = np.hstack([im, side])
    pred = CLASSES[int(act.argmax())]
    ok = pred == r["cls"]
    col = (60, 160, 60) if ok else (40, 40, 200)
    im = cv2.copyMakeBorder(im, 4, 26, 4, 4, cv2.BORDER_CONSTANT, value=col)
    cv2.putText(im, f"{pred} {act.max():.2f} | phone {ph.max():.2f}", (6, im.shape[0] - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    return im


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "v1"
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    for ds in ("syndd", "3mdad", "ebdd", "dad"):
        f = PRED / f"{tag}_{ds}_test.npz"
        if not f.exists():
            continue
        rs = rows(ds, "test")
        z = np.load(f)
        lines = []
        for c in CLASSES:
            idx = [k for k, r in enumerate(rs) if r["cls"] == c]
            if not idx:
                continue
            pick = rng.choice(idx, min(6, len(idx)), replace=False)
            ts = [tile(rs[k], z["act"][k], z["ph"][k]) for k in pick]
            while len(ts) < 6:
                ts.append(np.zeros_like(ts[0]))
            lab = np.full((ts[0].shape[0], 130, 3), 250, np.uint8)
            cv2.putText(lab, c, (6, ts[0].shape[0] // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (20, 20, 20), 1, cv2.LINE_AA)
            lines.append(np.hstack([lab, *ts]))
        sheet = np.vstack(lines)
        cv2.imwrite(str(OUT / f"examples_{tag}_{ds}.jpg"),
                    cv2.resize(sheet, None, fx=0.6, fy=0.6, interpolation=cv2.INTER_AREA),
                    [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ds in ("syndd", "3mdad"):
            idx = [k for k, r in enumerate(rs) if r["cls"] == "hand_on_face"]
            pick = rng.choice(idx, min(8, len(idx)), replace=False)
            ts = [tile(rs[k], z["act"][k], z["ph"][k], ears=True) for k in pick]
            sheet = np.vstack([np.hstack(ts[:4]), np.hstack(ts[4:8])])
            cv2.imwrite(str(OUT / f"hand_on_face_{tag}_{ds}.jpg"),
                        cv2.resize(sheet, None, fx=0.6, fy=0.6, interpolation=cv2.INTER_AREA),
                        [cv2.IMWRITE_JPEG_QUALITY, 85])
    print("written to", OUT)


if __name__ == "__main__":
    main()
