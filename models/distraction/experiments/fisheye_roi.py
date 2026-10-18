"""Item 3: SynDD frames -> what the detector sees on the Pi: a 160-degree equidistant fisheye
sensor (1296x972, OV5647 2x2 binned) at the mirror, then the live DriverROI rectification of the
driver's part of the frame (640x640, rtdms_distraction.roi exactly as live.py uses it).
No real calibration exists yet, so the lens is a generic equidistant one (diagonal FOV
150-170 deg, small random D), and the SynDD rear camera is placed 15-40 deg to the driver's side
of the fisheye axis (the mirror camera looks at the cabin centre).
python fisheye_roi.py <split> [share]   -> <data root>/det_v2/syndd_fish/{images,labels}/<split>"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import csv
import math
import sys
from pathlib import Path

import cv2
import numpy as np

from rtdms_distraction.calibration import FisheyeCalibration  # noqa: E402
from rtdms_distraction.roi import DriverROI, _boundary_points, _rays, virtual_camera  # noqa: E402

SRC = Path(f"{DATA}/det_v2/syndd")
OUT = Path(f"{DATA}/det_v2/syndd_fish")
SW, SH = 1296, 972
OUT_WH = 640


def rot(yaw, pitch):
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    return ry @ rx  # source camera axes expressed in the fisheye camera frame


def convert(img, boxes, rng):
    """img (H, W) gray, boxes [(c, x1, y1, x2, y2)] px -> (view 640x640 gray, boxes px) or None."""
    h, w = img.shape[:2]
    f_p = (w / 2) / math.tan(math.radians(rng.uniform(85, 105)) / 2)
    K_src = np.array([[f_p, 0, w / 2], [0, f_p, h / 2], [0, 0, 1.0]])
    half_diag = math.radians(rng.uniform(150, 170) / 2)
    f_fe = math.hypot(SW, SH) / 2 / half_diag
    K = np.array([[f_fe, 0, SW / 2 + rng.uniform(-15, 15)], [0, f_fe, SH / 2 + rng.uniform(-15, 15)],
                  [0, 0, 1.0]])
    D = rng.uniform(-0.01, 0.01, (4, 1))
    R = rot(math.radians(rng.uniform(10, 30)), math.radians(rng.uniform(-8, 8)))

    # fisheye sensor image: pixel -> ray (fisheye model) -> source camera -> source pixel
    # equidistant model: theta_d = theta (1 + k1 theta^2 + ...), theta_d = rho / f
    ys, xs = np.mgrid[0:SH, 0:SW].astype(np.float32)
    dx, dy = (xs - K[0, 2]) / f_fe, (ys - K[1, 2]) / f_fe
    theta_d = np.hypot(dx, dy)
    tt = np.linspace(0, math.radians(95), 4096)
    t2 = tt * tt
    d = D.ravel()
    td = tt * (1 + d[0] * t2 + d[1] * t2 ** 2 + d[2] * t2 ** 3 + d[3] * t2 ** 4)
    bad = np.nonzero(np.diff(td) <= 0)[0]
    if len(bad):  # keep the monotonic part only
        tt, td = tt[: bad[0] + 1], td[: bad[0] + 1]
    theta = np.interp(theta_d, td, tt).astype(np.float32)
    s = np.divide(np.sin(theta), theta_d, out=np.ones_like(theta), where=theta_d > 1e-9)
    ray = np.stack([dx * s, dy * s, np.cos(theta)], -1)  # unit rays, fisheye frame
    v = ray @ R.astype(np.float32)  # into the source camera frame (R columns = source axes)
    ok = (v[..., 2] > 1e-3) & (theta < math.radians(89))
    z = np.where(ok, v[..., 2], 1)
    u = np.where(ok, f_p * v[..., 0] / z + w / 2, -1).astype(np.float32)
    vv = np.where(ok, f_p * v[..., 1] / z + h / 2, -1).astype(np.float32)
    sensor = cv2.remap(img, u, vv, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

    def src_to_raw(p):  # (N, 2) source px -> fisheye sensor px
        r = np.concatenate([(p - K_src[:2, 2]) / f_p, np.ones((len(p), 1))], 1) @ R.T
        out, _ = cv2.fisheye.projectPoints(r.reshape(-1, 1, 3), np.zeros(3), np.zeros(3), K, D)
        return out.reshape(-1, 2)

    # driver ROI (as drawn with select_roi.py): the axis-aligned rectangle inscribed in where the
    # source's driver region lands on the sensor, so the view never reaches past the source
    t = np.linspace(0, 1, 16)
    xa, xb = rng.uniform(0.30, 0.40) * w, rng.uniform(0.97, 1.0) * w
    ya, yb = rng.uniform(0.0, 0.08) * h, rng.uniform(0.92, 1.0) * h
    top = src_to_raw(np.stack([xa + t * (xb - xa), np.full(16, ya)], 1))
    bot = src_to_raw(np.stack([xa + t * (xb - xa), np.full(16, yb)], 1))
    lef = src_to_raw(np.stack([np.full(16, xa), ya + t * (yb - ya)], 1))
    rig = src_to_raw(np.stack([np.full(16, xb), ya + t * (yb - ya)], 1))
    x1, x2 = lef[:, 0].max(), rig[:, 0].min()
    y1, y2 = top[:, 1].max(), bot[:, 1].min()
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(SW, x2), min(SH, y2)
    if x2 - x1 < 60 or y2 - y1 < 60:
        return None
    rect = [int(math.ceil(x1)), int(math.ceil(y1)), int(x2 - math.ceil(x1)), int(y2 - math.ceil(y1))]
    calib = FisheyeCalibration(K, D, SW, SH)
    try:
        Rv, _ = virtual_camera(calib, rect, OUT_WH, OUT_WH)
    except ValueError:
        return None
    v = _rays(_boundary_points(*rect), K, D) @ Rv.T
    su = np.ptp(v[:, 0] / v[:, 2])
    sv = np.ptp(v[:, 1] / v[:, 2])
    ow, oh = (OUT_WH, round(OUT_WH * sv / su)) if su >= sv else (round(OUT_WH * su / sv), OUT_WH)
    roi = DriverROI(SW, SH, rect, ow, oh, calib)
    view = roi.apply(sensor)

    nb = []
    tt = np.linspace(0, 1, 10)
    for c, x1, y1, x2, y2 in boxes:
        e = np.concatenate([np.stack([x1 + tt * (x2 - x1), np.full(10, y1)], 1),
                            np.stack([x1 + tt * (x2 - x1), np.full(10, y2)], 1),
                            np.stack([np.full(10, x1), y1 + tt * (y2 - y1)], 1),
                            np.stack([np.full(10, x2), y1 + tt * (y2 - y1)], 1)])
        o = roi.from_raw(src_to_raw(e))
        bx1, by1 = o.min(0)
        bx2, by2 = o.max(0)
        area = (bx2 - bx1) * (by2 - by1)
        cx1, cy1, cx2, cy2 = max(bx1, 0), max(by1, 0), min(bx2, roi.out_w), min(by2, roi.out_h)
        if area <= 0 or cx2 <= cx1 or cy2 <= cy1:
            continue
        if (cx2 - cx1) * (cy2 - cy1) / area < 0.5 or min(cx2 - cx1, cy2 - cy1) < 4:
            continue
        nb.append((c, cx1, cy1, cx2, cy2))
    return view, nb


def main(split, share=1.0):
    rng = np.random.default_rng(3)
    rows_in = [r for r in csv.DictReader(open(SRC / "meta.csv", encoding="utf8")) if r["split"] == split]
    rows_in = [r for r in rows_in if rng.random() < share]
    (OUT / "images" / split).mkdir(parents=True, exist_ok=True)
    (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)
    rows, skipped = [], 0
    for k, r in enumerate(rows_in):
        img = cv2.imread(str(SRC / "images" / r["image"]), cv2.IMREAD_GRAYSCALE)
        h, w = img.shape
        lab = (SRC / "labels" / r["image"]).with_suffix(".txt")
        boxes = []
        for ln in lab.read_text().splitlines():
            if ln.strip():
                c, x, y, bw, bh = map(float, ln.split())
                boxes.append((int(c), (x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w,
                              (y + bh / 2) * h))
        res = convert(img, boxes, rng)
        if res is None:
            skipped += 1
            continue
        view, nb = res
        vh, vw = view.shape[:2]
        if len(nb) < len(boxes):  # a box fell outside the driver view: drop the frame
            skipped += 1
            continue
        stem = Path(r["image"]).stem + "__fish"
        cv2.imwrite(str(OUT / "images" / split / f"{stem}.jpg"), view, [cv2.IMWRITE_JPEG_QUALITY, 90])
        (OUT / "labels" / split / f"{stem}.txt").write_text("".join(
            f"{c} {(a + b) / 2 / vw:.6f} {(d + e) / 2 / vh:.6f} {(b - a) / vw:.6f} "
            f"{(e - d) / vh:.6f}\n" for c, a, d, b, e in nb), encoding="utf8")
        rows.append({**r, "image": f"{split}/{stem}.jpg"})
        if k % 1000 == 0:
            print(k, len(rows_in), "skipped", skipped, flush=True)
    meta = OUT / f"meta_{split}.csv"
    with open(meta, "w", newline="", encoding="utf8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print("final", split, len(rows), "written,", skipped, "skipped", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 1.0)
