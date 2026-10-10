#!/usr/bin/env python3
"""Run the distraction pipeline on a camera or a video, with overlay and JSONL event log.

    python scripts/run.py                              # Pi camera (or webcam on a PC)
    python scripts/run.py --video clip.mp4 --no-rectify --roi 640,0,640,720
    python scripts/run.py --video clip.mp4 --no-display --save-video out.mp4
    python scripts/run.py --detector-backend ultralytics --weights yolo26n.pt   # PC

Keys: q / Esc quit, space pause (video), b reset baseline.
Public, non-fisheye datasets (SynDD, YawDD, DMD): always pass --no-rectify.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rtdms_distraction.capture import open_source  # noqa: E402
from rtdms_distraction.config import (  # noqa: E402
    load_pipeline_config,
    load_rules_config,
    resolve_path,
)
from rtdms_distraction.eventlog import EventLog  # noqa: E402
from rtdms_distraction.pipeline import DistractionPipeline  # noqa: E402
from rtdms_distraction.rules import Baseline  # noqa: E402
from rtdms_distraction.viz import render  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--config", help="pipeline.yaml (default configs/pipeline.yaml)")
    p.add_argument("--rules", help="rules.yaml (default configs/rules.yaml)")
    p.add_argument("--video", help="video file instead of a live camera")
    p.add_argument("--camera-index", type=int, help="OpenCV webcam index (forces webcam)")
    p.add_argument("--realtime", action="store_true", help="pace a video at its own frame rate")
    p.add_argument("--no-rectify", action="store_true", help="non-fisheye source: plain crop")
    p.add_argument("--roi", help="override roi.rect: x,y,w,h in raw pixels ('full' = whole frame)")
    p.add_argument("--driver-side", choices=["right", "left"])
    p.add_argument("--detector-backend", choices=["ncnn", "onnx", "ultralytics"])
    p.add_argument("--weights", help="override detector.weights")
    p.add_argument("--detect-every", type=int, help="run the detector every Nth frame")
    p.add_argument("--hands", choices=["mediapipe", "detector", "off"])
    p.add_argument("--no-display", action="store_true")
    p.add_argument("--save-video", help="write the overlay to this .mp4")
    p.add_argument("--per-frame-log", action="store_true", help="also log every frame (JSONL)")
    p.add_argument("--log-dir", help="override eventlog.dir")
    p.add_argument("--duration", type=float, help="stop after N seconds of stream time")
    p.add_argument("--print-every", type=float, default=1.0, help="console status period, s")
    return p.parse_args(argv)


def apply_overrides(pcfg, args) -> None:
    if args.no_rectify:
        pcfg.rectify.enabled = False
    if args.roi:
        pcfg.roi.rect = None if args.roi == "full" else [int(v) for v in args.roi.split(",")]
    if args.driver_side:
        pcfg.driver_side = args.driver_side
    if args.detector_backend:
        pcfg.detector.backend = args.detector_backend
    if args.weights:
        pcfg.detector.weights = args.weights
    if args.detect_every:
        pcfg.detector.every_n = args.detect_every
    if args.hands:
        pcfg.hands.source = args.hands
    if args.per_frame_log:
        pcfg.eventlog.per_frame = True
    if args.log_dir:
        pcfg.eventlog.dir = args.log_dir


def main(argv=None) -> int:
    args = parse_args(argv)
    pcfg = load_pipeline_config(args.config)
    rcfg = load_rules_config(args.rules)
    apply_overrides(pcfg, args)
    c = pcfg.capture

    src = open_source(c.width, c.height, c.fps, video=args.video, camera_index=args.camera_index,
                      flip=c.flip_horizontal, realtime=args.realtime)
    src.start()
    pipe = DistractionPipeline(pcfg, rcfg, src.size)
    log = EventLog(resolve_path(pcfg.eventlog.dir), pcfg.eventlog.per_frame)
    log.session(source=src.describe(), driver_side=pcfg.driver_side,
                rectified=pipe.roi.rectified, roi=pipe.roi.rect,
                detector=f"{pcfg.detector.backend}:{pcfg.detector.weights}",
                facemesh=pcfg.facemesh.backend, hands=pcfg.hands.source)
    print(f"[run] {src.describe()} -> view {pipe.roi.out_w}x{pipe.roi.out_h} "
          f"({'rectified' if pipe.roi.rectified else 'crop'}), log {log.path}")

    writer = None
    n, t_first, t_last_print, last_t = 0, None, -1e9, None
    fps_t0, fps = time.perf_counter(), 0.0
    paused = False
    try:
        while True:
            if not paused:
                gray, t = src.read()
                if gray is None:
                    break
                if t_first is None:
                    t_first = t
                if args.duration and t - t_first >= args.duration:
                    break
                res = pipe.process(gray, t)
                n += 1
                last_t = t
                for e in log.update(t, res.behaviours):
                    print(f"[event] t={e['t']:.2f} {e['event']} {e['behaviour']} "
                          f"{e.get('level', e.get('peak_level', ''))}")
                log.frame(res.to_dict())
                if n % 15 == 0:
                    now = time.perf_counter()
                    fps, fps_t0 = 15 / (now - fps_t0), now
                if t - t_last_print >= args.print_every:
                    t_last_print = t
                    active = [f"{b}:{s['level']}" for b, s in res.behaviours.items()
                              if s["level"] != "none"]
                    face = "face" if res.face is not None else "NO FACE"
                    print(f"[t={t - t_first:6.1f}s] {fps:5.1f} fps  {face:7s} "
                          f"baseline {res.baseline['progress']:.0%}  "
                          f"{' '.join(active) or 'normal'}")
            if args.no_display and not args.save_video:
                continue
            frame = render(res, fps, rcfg.phone_in_hand.holder_zones)
            if args.save_video:
                if writer is None:
                    rate = getattr(src, "fps", c.fps)
                    writer = cv2.VideoWriter(args.save_video, cv2.VideoWriter_fourcc(*"mp4v"),
                                             rate, (frame.shape[1], frame.shape[0]))
                writer.write(frame)
            if not args.no_display:
                cv2.imshow("rtdms-distraction", frame)
                k = cv2.waitKey(1) & 0xFF
                if k in (27, ord("q")):
                    break
                if k == ord(" "):
                    paused = not paused
                if k == ord("b"):
                    b = rcfg.baseline
                    pipe.rules.baseline = Baseline(b.duration_s, b.min_samples)
                    print("[run] baseline reset")
    except KeyboardInterrupt:
        pass
    finally:
        log.close(last_t)
        src.stop()
        pipe.close()
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()
    print(f"[run] {n} frames; events in {log.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
