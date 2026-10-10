#!/usr/bin/env python3
"""Record a clip + metadata for tuning and dataset building.

    # PC webcam, guided: on-screen prompts tell the subject what to do and when (colour video)
    python scripts/record.py --camera-index 0 --subject S01 --scenario guided --guided

    # Pi camera, headless, free-form scenario (grayscale Y plane at 1296x972)
    python scripts/record.py --subject S01 --scenario phone_left_ear --lighting night --seconds 60

Output: data/recordings/<subject>_<scenario>_<lighting>_<utc>.mp4 + .json (metadata, and for
--guided the prompt timeline, which doubles as a rough label track).
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rtdms_distraction.capture import is_raspberry_pi, open_source  # noqa: E402
from rtdms_distraction.config import PACKAGE_ROOT, load_pipeline_config  # noqa: E402

# (start_s, end_s, label, prompt)
GUIDED = [
    (0, 8, "normal", "Look at the screen normally (baseline)"),
    (8, 18, "phone_in_hand", "Hold PHONE LOW in your hand and text / look at it"),
    (18, 26, "normal", "Put the phone down, look normally"),
    (26, 34, "phone_right_ear", "Phone call at your RIGHT ear"),
    (34, 40, "normal", "Phone down"),
    (40, 48, "phone_left_ear", "Phone call at your LEFT ear"),
    (48, 54, "normal", "Phone down, pick up a cup or bottle"),
    (54, 62, "drinking", "DRINK from the cup / bottle (2-3 sips)"),
    (62, 68, "normal", "Cup down"),
    (68, 78, "eating", "EAT something and chew (lips closed)"),
    (78, 86, "talking", "TALK out loud (no food)"),
    (86, 92, "nod_turn", "Nod down-up twice, then turn left-right"),
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--subject", default="S00")
    p.add_argument("--scenario", default="free")
    p.add_argument("--lighting", default="day", choices=["day", "night", "dusk"])
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--camera-index", type=int)
    p.add_argument("--guided", action="store_true", help="on-screen prompt sequence (PC)")
    p.add_argument("--no-display", action="store_true")
    p.add_argument("--notes", default="")
    args = p.parse_args()

    pcfg = load_pipeline_config()
    c = pcfg.capture
    pi = args.camera_index is None and is_raspberry_pi()
    if pi:
        src = open_source(c.width, c.height, c.fps).start()  # grayscale Y plane
        fps = c.fps
    else:  # webcam: keep colour so colour-vs-gray can be compared offline
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        cap = cv2.VideoCapture(args.camera_index or 0, backend)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        if not cap.isOpened():
            raise SystemExit("cannot open webcam")
        fps = 30

    if args.guided:
        args.seconds = GUIDED[-1][1]
    out_dir = PACKAGE_ROOT / "data" / "recordings"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stem = out_dir / f"{args.subject}_{args.scenario}_{args.lighting}_{stamp}"
    writer = None
    show = not args.no_display

    def grab():
        if pi:
            g, _ = src.read()
            return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
        ok, f = cap.read()
        return f if ok else None

    # Wait for SPACE so the subject is ready (display only).
    if show:
        while True:
            f = grab()
            msg = "SPACE = start recording   q = quit"
            cv2.putText(f, msg, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            cv2.imshow("record", f)
            k = cv2.waitKey(1) & 0xFF
            if k == ord(" "):
                break
            if k in (27, ord("q")):
                return 1

    t0 = time.monotonic()
    n = 0
    while True:
        t = time.monotonic() - t0
        if t >= args.seconds:
            break
        f = grab()
        if f is None:
            continue
        if writer is None:
            h, w = f.shape[:2]
            writer = cv2.VideoWriter(str(stem.with_suffix(".mp4")),
                                     cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        writer.write(f)
        n += 1
        if show:
            disp = f.copy()
            cv2.circle(disp, (30, 30), 10, (0, 0, 255), -1)
            cv2.putText(disp, f"REC {t:5.1f}s", (50, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                        (0, 0, 255), 2)
            if args.guided:
                for a, b, _, prompt in GUIDED:
                    if a <= t < b:
                        cv2.rectangle(disp, (0, disp.shape[0] - 70), (disp.shape[1],
                                      disp.shape[0]), (0, 0, 0), -1)
                        cv2.putText(disp, f"{prompt}  ({b - t:.0f}s)", (20, disp.shape[0] - 25),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
            cv2.imshow("record", disp)
            if (cv2.waitKey(1) & 0xFF) in (27, ord("q")):
                break
    elapsed = time.monotonic() - t0
    if writer is not None:
        writer.release()
    if pi:
        src.stop()
    else:
        cap.release()
    cv2.destroyAllWindows()

    meta = {
        "subject": args.subject, "scenario": args.scenario, "lighting": args.lighting,
        "utc": stamp, "frames": n, "seconds": round(elapsed, 2),
        # Real capture rate: webcams often deliver less than they promise. Replays must use it.
        "measured_fps": round(n / elapsed, 2) if elapsed else None,
        "source": "picamera2 Y" if pi else f"webcam #{args.camera_index or 0} BGR",
        "notes": args.notes,
        "timeline": [{"start": a, "end": b, "label": lab} for a, b, lab, _ in GUIDED]
        if args.guided else [],
    }
    stem.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf8")
    print(f"saved {stem.with_suffix('.mp4')} ({n} frames, {meta['measured_fps']} fps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
