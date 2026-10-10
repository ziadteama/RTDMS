#!/usr/bin/env python3
"""Event-level evaluation of the FULL pipeline (detector + face mesh + rules + smoothing).

    # our guided clip (labels = record.py prompt timeline)
    python scripts/eval_events.py s01 --src data/recordings/S01_guided_day_<utc>.mp4 \
        --weights D:/rtdms-data/runs/v1_416/weights/best_ncnn_model
    # public sets through their adapters (test drivers only, see --drivers)
    python scripts/eval_events.py yawdd --src data/public/yawdd --weights ...
    python scripts/eval_events.py syndd --src D:/datasets/SynDD2 --drivers syndd_24026,...

Per behaviour: an alert EVENT is a true positive if it overlaps a labelled segment of the same
behaviour (with --slack seconds of tolerance), else a false alarm. A labelled segment is detected
if any matching event overlaps it; time-to-alert = event start - segment start.
False alarms per hour are counted over normal + hard-negative time (talking, singing, ...).
Non-fisheye sources run with rectification off and the whole frame as ROI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rtdms_distraction import datasets as D  # noqa: E402
from rtdms_distraction.capture import VideoFileSource  # noqa: E402
from rtdms_distraction.config import (  # noqa: E402
    BEHAVIOURS,
    load_pipeline_config,
    load_rules_config,
)
from rtdms_distraction.pipeline import DistractionPipeline  # noqa: E402


def s01_segments(video: Path) -> list[D.Segment]:
    meta = json.loads(video.with_suffix(".json").read_text(encoding="utf8"))
    lab = {"talking": "neg_talking", "nod_turn": "normal"}
    return [D.Segment("s01", meta["subject"], video, s["start"], s["end"],
                      lab.get(s["label"], s["label"])) for s in meta["timeline"]]


def run_video(video: Path, pcfg, rcfg) -> list[dict]:
    src = VideoFileSource(video).start()
    pipe = DistractionPipeline(pcfg, rcfg, src.size)
    events, open_ = [], {}
    t = 0.0
    while True:
        gray, ts = src.read()
        if gray is None:
            break
        t = ts
        res = pipe.process(gray, ts)
        for b, st in res.behaviours.items():
            if st["level"] != "none" and b not in open_:
                open_[b] = {"behaviour": b, "start": ts, "peak": st["level"]}
            elif st["level"] != "none":
                if st["level"] == "alert":
                    open_[b]["peak"] = "alert"
            elif b in open_:
                e = open_.pop(b)
                e["end"] = ts
                events.append(e)
    for e in open_.values():
        e["end"] = t
        events.append(e)
    src.stop()
    pipe.close()
    return events


def score(segments: list[D.Segment], events_by_video: dict, slack: float) -> dict:
    out = {}
    neg_time = sum(s.end_s - s.start_s for s in segments
                   if s.label == "normal" or s.label.startswith("neg_"))
    for b in BEHAVIOURS:
        segs = [s for s in segments if s.label == b]
        tp = fp = 0
        detected, delays = set(), []
        for video, evs in events_by_video.items():
            vsegs = [s for s in segs if s.video == video]
            for e in (x for x in evs if x["behaviour"] == b):
                hit = [s for s in vsegs if e["start"] < s.end_s + slack and
                       e["end"] > s.start_s - slack]
                if hit:
                    tp += 1
                    for s in hit:
                        if s not in detected:
                            detected.add(s)
                            delays.append(max(0.0, e["start"] - s.start_s))
                else:
                    fp += 1
        n = len(segs)
        p = tp / (tp + fp) if tp + fp else None
        r = len(detected) / n if n else None
        f1 = 2 * p * r / (p + r) if p and r else (0.0 if n else None)
        out[b] = {"segments": n, "events": tp + fp, "precision": _r(p), "recall": _r(r),
                  "f1": _r(f1), "false_alarms": fp,
                  "false_alarms_per_hour_neg": _r(fp / (neg_time / 3600)) if neg_time else None,
                  "median_time_to_alert_s": _r(sorted(delays)[len(delays) // 2])
                  if delays else None}
    out["_neg_time_s"] = round(neg_time, 1)
    return out


def _r(v):
    return None if v is None else round(float(v), 3)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("dataset", choices=["s01", "ours", "syndd", "dmd", "yawdd"])
    p.add_argument("--src", required=True)
    p.add_argument("--weights", help="detector weights (NCNN folder, .onnx or .pt)")
    p.add_argument("--backend", default=None, choices=["ncnn", "onnx", "ultralytics"])
    p.add_argument("--drivers", help="comma list: only these drivers (e.g. the test split)")
    p.add_argument("--max-videos", type=int)
    p.add_argument("--slack", type=float, default=1.0)
    p.add_argument("--hands", choices=["mediapipe", "detector", "off"])
    p.add_argument("--imgsz", type=int, help="detector input size (default from pipeline.yaml)")
    p.add_argument("--json")
    args = p.parse_args()

    pcfg, rcfg = load_pipeline_config(), load_rules_config()
    pcfg.rectify.enabled = False
    pcfg.roi.rect = None
    if args.weights:
        pcfg.detector.weights = args.weights
        pcfg.detector.backend = args.backend or (
            "ncnn" if Path(args.weights).is_dir() else
            "onnx" if args.weights.endswith(".onnx") else "ultralytics")
    if args.hands:
        pcfg.hands.source = args.hands
    if args.imgsz:
        pcfg.detector.imgsz = args.imgsz

    if args.dataset == "s01":
        segments = s01_segments(Path(args.src))
    else:
        segments = [s for s in D.ADAPTERS[args.dataset](args.src) if isinstance(s, D.Segment)]
    if args.drivers:
        keep = set(args.drivers.split(","))
        segments = [s for s in segments if s.driver in keep]
    videos = sorted({s.video for s in segments})[: args.max_videos]
    segments = [s for s in segments if s.video in videos]

    events_by_video = {}
    for i, v in enumerate(videos, 1):
        events_by_video[v] = run_video(v, pcfg, rcfg)
        print(f"[{i}/{len(videos)}] {v.name}: {len(events_by_video[v])} events", flush=True)
    result = {"dataset": args.dataset, "detector": f"{pcfg.detector.backend}:"
              f"{pcfg.detector.weights}", "hands": pcfg.hands.source, "videos": len(videos),
              "scores": score(segments, events_by_video, args.slack),
              "events": {str(k): v for k, v in events_by_video.items()}}
    print(f"\n{'behaviour':16s} {'segs':>4s} {'events':>6s} {'P':>6s} {'R':>6s} {'F1':>6s} "
          f"{'FA':>4s} {'FA/h':>7s} {'TTA s':>6s}")
    for b in BEHAVIOURS:
        s = result["scores"][b]
        print(f"{b:16s} {s['segments']:4d} {s['events']:6d} "
              + " ".join(f"{'-' if s[k] is None else s[k]:>6}" for k in
                         ("precision", "recall", "f1"))
              + f" {s['false_alarms']:4d} {str(s['false_alarms_per_hour_neg']):>7s} "
              f"{str(s['median_time_to_alert_s']):>6s}")
    print(f"normal + negative time: {result['scores']['_neg_time_s']} s")
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, default=str), encoding="utf8",
                                   newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
