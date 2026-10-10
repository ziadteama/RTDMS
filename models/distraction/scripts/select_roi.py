#!/usr/bin/env python3
"""Pick the driver ROI on a raw frame and save it to configs/pipeline.yaml (roi.rect).

    # interactive (needs a display): drag a box around the driver's head, shoulders and hands
    python scripts/select_roi.py --image data/cabin.png
    python scripts/select_roi.py --video data/drive.mp4 --frame 300

    # headless Pi: save a raw frame, pick the ROI on a PC, or pass it numerically
    python scripts/select_roi.py --grab data/cabin.png
    python scripts/select_roi.py --image data/cabin.png --rect 620,80,640,760 --preview roi.png

Include the space the hands use: both ears, the mouth, the lap and the steering wheel rim.
Leave out the passenger seat as far as possible; mask_polygons can blank what remains.
With rectification on, the preview shows the corrected view the detector will see.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rtdms_distraction.calibration import FisheyeCalibration  # noqa: E402
from rtdms_distraction.capture import open_source, to_gray  # noqa: E402
from rtdms_distraction.config import load_pipeline_config, resolve_path, save_roi_rect  # noqa: E402
from rtdms_distraction.roi import DriverROI  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--image")
    p.add_argument("--video")
    p.add_argument("--frame", type=int, default=0, help="video frame index")
    p.add_argument("--camera-index", type=int)
    p.add_argument("--grab", help="just save one raw camera frame here and exit")
    p.add_argument("--rect", help="x,y,w,h instead of drawing")
    p.add_argument("--no-rectify", action="store_true")
    p.add_argument("--preview", help="write raw+ROI and the driver view side by side here")
    p.add_argument("--no-save", action="store_true", help="do not modify pipeline.yaml")
    return p.parse_args()


def load_frame(args, pcfg) -> np.ndarray:
    if args.image:
        img = cv2.imread(args.image, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise SystemExit(f"cannot read {args.image}")
        return img
    if args.video:
        cap = cv2.VideoCapture(args.video)
        cap.set(cv2.CAP_PROP_POS_FRAMES, args.frame)
        ok, frame = cap.read()
        if not ok:
            raise SystemExit(f"cannot read frame {args.frame} of {args.video}")
        return to_gray(frame)
    c = pcfg.capture
    with open_source(c.width, c.height, c.fps, camera_index=args.camera_index) as src:
        for _ in range(10):  # let exposure settle
            gray, _ = src.read()
        return gray.copy()


def main() -> int:
    args = parse_args()
    pcfg = load_pipeline_config()
    raw = load_frame(args, pcfg)
    if args.grab:
        Path(args.grab).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(args.grab, raw)
        print(f"saved raw {raw.shape[1]}x{raw.shape[0]} frame to {args.grab}")
        return 0

    if args.rect:
        rect = [int(v) for v in args.rect.split(",")]
    else:
        scale = min(1.0, 1400 / raw.shape[1])
        shown = cv2.resize(raw, None, fx=scale, fy=scale)
        x, y, w, h = cv2.selectROI("driver ROI (ENTER to accept)", shown, showCrosshair=False)
        cv2.destroyAllWindows()
        if w == 0 or h == 0:
            print("no ROI selected")
            return 1
        rect = [round(v / scale) for v in (x, y, w, h)]

    calib = None
    if pcfg.rectify.enabled and not args.no_rectify:
        path = resolve_path(pcfg.rectify.calibration_file)
        if path.is_file():
            calib = FisheyeCalibration.load(path)
        else:
            print(f"note: {path} missing, previewing as a plain crop")
    roi = DriverROI(raw.shape[1], raw.shape[0], rect, pcfg.roi.output_width,
                    pcfg.roi.output_height, calib, pcfg.roi.mask_polygons)
    view = roi.apply(raw)

    # Outline what the driver view covers, traced back into the raw frame.
    left = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
    w, h = roi.out_w, roi.out_h
    edge = np.concatenate([
        np.stack([np.linspace(0, w, 50), np.zeros(50)], 1),
        np.stack([np.full(50, w), np.linspace(0, h, 50)], 1),
        np.stack([np.linspace(w, 0, 50), np.full(50, h)], 1),
        np.stack([np.zeros(50), np.linspace(h, 0, 50)], 1),
    ])
    outline = roi.to_raw(edge).round().astype(np.int32)
    cv2.polylines(left, [outline], True, (0, 255, 0), 2)
    x, y, rw, rh = rect
    cv2.rectangle(left, (x, y), (x + rw, y + rh), (0, 200, 255), 1)
    right = cv2.cvtColor(view, cv2.COLOR_GRAY2BGR)
    s = left.shape[0] / right.shape[0]
    right = cv2.resize(right, (round(right.shape[1] * s), left.shape[0]))
    both = np.hstack([left, right])

    if args.preview:
        cv2.imwrite(args.preview, both)
        print(f"preview -> {args.preview}")
    elif not args.rect:
        cv2.imshow("ROI preview (any key)", cv2.resize(both, None, fx=0.6, fy=0.6))
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    print(f"roi.rect = {rect}  -> driver view {roi.out_w}x{roi.out_h} "
          f"({'rectified' if roi.rectified else 'crop'})")
    if not args.no_save:
        save_roi_rect(rect)
        print("saved to configs/pipeline.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
