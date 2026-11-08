"""Idea C: second detector pass on a head-and-shoulders crop taken from the 1280x720 capture.
python crop_pass.py <split> <scale fw> <imgsz> ; caches boxes in VIEW coordinates (640x360)."""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from rtdms_distraction import datasets as D  # noqa: E402

W = f"{DATA}/runs/det_v2d_ir_512/weights/best.pt"


def run(video: str, scale: float, imgsz: int, out: str) -> str:
    if Path(out).is_file():
        return out
    from ultralytics import YOLO

    m = YOLO(W)
    fz = np.load(f"{DATA}/eval_cache/faces/fps10/{Path(video).stem}.npz")
    ok, lm_all = fz["ok"], fz["lm"]
    cap = cv2.VideoCapture(video)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(src_fps / 10))
    rows, i, k, last = [], 0, 0, None
    while True:
        if i % step:
            if not cap.grab():
                break
            i += 1
            continue
        good, f = cap.read()
        if not good:
            break
        t = i / src_fps
        i += 1
        if k < len(ok) and ok[k]:
            last = lm_all[k]
        k += 1
        if last is None:
            continue
        cap_img = cv2.resize(f, (1280, 720), interpolation=cv2.INTER_AREA)
        s = 2.0  # view (640x360) -> capture (1280x720)
        fw = float(np.linalg.norm(last[234] - last[454])) * s
        cx, cy = last[[1, 152]].mean(0) * s
        half = max(40.0, scale * fw / 2)
        x0, y0 = int(max(0, cx - half)), int(max(0, cy - half * 0.8))
        x1, y1 = int(min(1280, cx + half)), int(min(720, cy + half * 1.2))
        if x1 - x0 < 32 or y1 - y0 < 32:
            continue
        r = m.predict(cap_img[y0:y1, x0:x1], imgsz=imgsz, conf=0.05, verbose=False)[0]
        for (a, b, c, d), cls, cf in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.cls.cpu().numpy(),
                                         r.boxes.conf.cpu().numpy(), strict=True):
            rows.append((t, int(cls), float(cf), (a + x0) / s, (b + y0) / s, (c + x0) / s,
                         (d + y0) / s))
    cap.release()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    np.save(out, np.array(rows, np.float64).reshape(-1, 7))
    return out


if __name__ == "__main__":
    split_name, scale, imgsz = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])
    split = json.load(open(str(REPO / "configs/syndd_split.json")))
    segs = [s for s in D.syndd(f"{DATA}/public/syndd/A1") if split.get(s.driver) == split_name]
    videos = sorted({str(s.video) for s in segs})
    tag = f"crop_s{scale:g}_{imgsz}"
    outs = [f"{DATA}/eval_cache/dets/det_v2d_{tag}/fps10/{Path(v).stem}.npy" for v in videos]
    with ProcessPoolExecutor(3) as ex:
        list(ex.map(run, videos, [scale] * len(videos), [imgsz] * len(videos), outs))
    print("crop dets cached:", tag, len(videos))
