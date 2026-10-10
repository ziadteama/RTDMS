#!/usr/bin/env python3
"""Fisheye calibration from a printed checkerboard -> configs/camera_fisheye.yaml (K, D).

Capture at the SAME resolution the pipeline runs at (1296x972 by default).

    # live with a display: SPACE grabs a view when the board is found, c calibrates
    python scripts/calibrate_fisheye.py --pattern 9x6 --square 0.025

    # headless Pi: grabs a view automatically every --interval s while the board is visible
    python scripts/calibrate_fisheye.py --headless --views 25 --save-views data/calib

    # offline: a folder of images, or a video sampled every 15th frame
    python scripts/calibrate_fisheye.py --images data/calib/*.png --pattern 9x6 --square 0.025
    python scripts/calibrate_fisheye.py --video data/calib.mp4 --every 15 --pattern 9x6

--pattern is INNER corners (cols x rows): a board of 10x7 squares has 9x6 inner corners.
Aim for 20+ views: tilt the board, and put it in the corners and edges of the frame. The edges
are where a 160-degree lens distorts most and where the driver sits.
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rtdms_distraction.calibration import calibrate, find_corners  # noqa: E402
from rtdms_distraction.capture import open_source, to_gray  # noqa: E402
from rtdms_distraction.config import load_pipeline_config, resolve_path  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--pattern", default="9x6", help="inner corners, cols x rows")
    p.add_argument("--square", type=float, default=0.025, help="square size (metres)")
    p.add_argument("--images", nargs="*", help="image files / globs")
    p.add_argument("--video", help="calibration video")
    p.add_argument("--every", type=int, default=15, help="video: use every Nth frame")
    p.add_argument("--camera-index", type=int, help="force an OpenCV webcam")
    p.add_argument("--out", default=None, help="output YAML (default: rectify.calibration_file)")
    p.add_argument("--save-views", help="live mode: also save grabbed frames to this folder")
    p.add_argument("--min-views", type=int, default=12)
    p.add_argument("--headless", action="store_true", help="live, no window: auto-grab views")
    p.add_argument("--views", type=int, default=25, help="headless: views to grab")
    p.add_argument("--interval", type=float, default=1.5, help="headless: seconds between grabs")
    return p.parse_args()


def offline_frames(args):
    if args.images:
        files = sorted({f for g in args.images for f in glob.glob(g)})
        for f in files:
            img = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                yield f, img
    else:
        cap = cv2.VideoCapture(args.video)
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % args.every == 0:
                yield f"frame{i}", to_gray(frame)
            i += 1


def live_views(args, pattern, size):
    src = open_source(size[0], size[1], 15, camera_index=args.camera_index).start()
    views = []
    save = Path(args.save_views) if args.save_views else None
    if save:
        save.mkdir(parents=True, exist_ok=True)
    print("headless: move the board around the frame" if args.headless
          else "SPACE: grab view   c: calibrate   q: quit")
    last = -1e9
    try:
        while True:
            gray, t = src.read()
            corners = find_corners(gray, pattern)
            if args.headless:
                if corners is not None and t - last >= args.interval:
                    last = t
                    views.append(corners)
                    if save:
                        cv2.imwrite(str(save / f"view_{len(views):03d}.png"), gray)
                    print(f"grabbed view {len(views)}/{args.views}")
                if len(views) >= args.views:
                    break
                continue
            show = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            if corners is not None:
                cv2.drawChessboardCorners(show, pattern, corners, True)
            cv2.putText(show, f"views: {len(views)}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                        (0, 255, 0), 2)
            cv2.imshow("calibrate", cv2.resize(show, None, fx=0.6, fy=0.6))
            k = cv2.waitKey(1) & 0xFF
            if k == ord(" ") and corners is not None:
                views.append(corners)
                if save:
                    cv2.imwrite(str(save / f"view_{len(views):03d}.png"), gray)
                print(f"grabbed view {len(views)}")
            elif k == ord("c"):
                break
            elif k in (27, ord("q")):
                raise SystemExit(1)
    finally:
        src.stop()
        cv2.destroyAllWindows()
    return views, src.size


def main() -> int:
    args = parse_args()
    pattern = tuple(int(v) for v in args.pattern.lower().split("x"))
    pcfg = load_pipeline_config()
    size = (pcfg.capture.width, pcfg.capture.height)

    if args.images or args.video:
        views, img_size = [], None
        for name, gray in offline_frames(args):
            img_size = img_size or (gray.shape[1], gray.shape[0])
            if (gray.shape[1], gray.shape[0]) != img_size:
                print(f"skip {name}: size differs")
                continue
            c = find_corners(gray, pattern)
            print(f"{name}: {'ok' if c is not None else 'no board'}")
            if c is not None:
                views.append(c)
    else:
        views, img_size = live_views(args, pattern, size)

    if len(views) < args.min_views:
        print(f"only {len(views)} usable views; need >= {args.min_views}")
        return 1
    # CALIB_CHECK_COND rejects degenerate views by raising; drop them one at a time.
    while True:
        try:
            calib = calibrate(views, pattern, args.square, img_size)
            break
        except cv2.error as e:
            msg = str(e)
            idx = [int(s) for s in msg.split() if s.isdigit()]
            if "CALIB_CHECK_COND" not in msg or not idx or len(views) <= args.min_views:
                raise
            print(f"dropping ill-conditioned view {idx[-1]}")
            views.pop(idx[-1])

    out = Path(args.out) if args.out else resolve_path(pcfg.rectify.calibration_file)
    calib.save(out)
    print(f"RMS reprojection error {calib.rms:.3f} px over {calib.n_images} views")
    print(f"K =\n{np.array2string(calib.K, precision=2)}\nD = {calib.D.ravel()}")
    print(f"saved {out}")
    if calib.rms > 1.0:
        print("WARNING: RMS > 1 px. Retake views (sharper, more board tilt, cover the edges).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
