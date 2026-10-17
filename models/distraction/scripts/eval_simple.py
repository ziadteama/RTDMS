#!/usr/bin/env python3
"""Alert-level test of SIMPLE mode (one detector + three rules) on whole SynDD rear-view videos
of held-out drivers. TRAINING ENV (GPU).

    python scripts/eval_simple.py --models det_v2b=D:/rtdms-data/runs/det_v2b_416/weights/best.pt \
        --split test --out D:/rtdms-data/runs/eval_simple

Per video (frames at --fps, resized to the laptop 1280x720 capture, then the live driver view):
  pass 1 (once, cached): face mesh -> landmarks per frame        <cache>/faces/<video>.npz
  pass 2 (per model, cached): detector boxes per frame           <cache>/dets/<model>/<video>.npz
  replay: simple_rules.SimpleRules on (t, face, boxes)  -> alert intervals per behaviour
Scoring per labelled behaviour (phone right ear / left ear / in hand -> 'phone' alerts, drinking,
eating): recall = share of segments with an alert overlapping them (1 s slack); time to alert =
first alert start - segment start (0 if already on); false alarms = alert events that start
inside a negative segment (normal driving and look-alikes: talking, singing, yawning, hand on
head, reaching, control panel; pick-up is ignored) and overlap no positive segment of that
behaviour; per hour of negative time. Ranges: 5-95 % over 1000 bootstrap resamples of drivers.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rtdms_distraction import datasets as D  # noqa: E402
from rtdms_distraction.config import load_pipeline_config, load_rules_config  # noqa: E402
from rtdms_distraction.roi import DriverROI  # noqa: E402
from rtdms_distraction.simple_rules import SimpleRules  # noqa: E402
from rtdms_distraction.types import Box, Detection, FaceObservation  # noqa: E402

CAPTURE = (1280, 720)
ROWS = {"phone_right_ear": "phone", "phone_left_ear": "phone", "phone_in_hand": "phone",
        "drinking": "drinking", "eating": "eating"}
NAMES = ["phone", "drink", "food"]
# SynDD "pick up from floor" often involves a phone (the teacher saw a real phone in 40 of 83
# frames the detector flagged there), so it is neither a positive nor phone-free time.
IGNORED = {"neg_pickup"}


def is_negative(label: str) -> bool:
    return label == "normal" or (label.startswith("neg_") and label not in IGNORED)


def frames(video: Path, fps: float):
    """(t, driver view BGR) at ~fps, through the live geometry (capture size -> ROI view)."""
    pcfg = load_pipeline_config(profile="laptop_webcam")
    r = pcfg.roi
    roi = DriverROI(CAPTURE[0], CAPTURE[1], r.rect, r.output_width, r.output_height, None,
                    r.mask_polygons)
    cap = cv2.VideoCapture(str(video))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(src_fps / fps))
    i = 0
    while True:
        if i % step:
            if not cap.grab():
                break
            i += 1
            continue
        ok, f = cap.read()
        if not ok:
            break
        yield i / src_fps, roi.apply(cv2.resize(f, CAPTURE, interpolation=cv2.INTER_AREA))
        i += 1
    cap.release()


def face_pass(video: str, fps: float, out: str) -> str:
    out_p = Path(out)
    if out_p.is_file():
        return out
    from rtdms_distraction.facemesh import FaceMesh

    pcfg = load_pipeline_config(profile="laptop_webcam")
    mesh, ts, lms, ok = None, [], [], []
    for t, view in frames(Path(video), fps):
        if mesh is None:
            h, w = view.shape[:2]
            mesh = FaceMesh(pcfg.facemesh, w, h, np.array([[w, 0, w / 2], [0, w, h / 2],
                                                          [0, 0, 1.0]]))
        f = mesh.process(cv2.cvtColor(view, cv2.COLOR_BGR2RGB), t)
        ts.append(t)
        ok.append(f is not None)
        lms.append(f.landmarks[:, :2].astype(np.float32) if f is not None
                   else np.zeros((478, 2), np.float32))
    if mesh is not None:
        mesh.close()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_p, t=np.array(ts), ok=np.array(ok), lm=np.array(lms))
    return out


def det_pass(video: str, fps: float, weights: str, imgsz: int, out: str) -> str:
    out_p = Path(out)
    if out_p.is_file():
        return out
    from ultralytics import YOLO

    m = YOLO(weights)
    rows, batch, bt = [], [], []

    def flush():
        for t, r in zip(bt, m.predict(batch, imgsz=imgsz, conf=0.05, verbose=False),
                        strict=True):
            for (a, b, c, d), k, cf in zip(r.boxes.xyxy.cpu().numpy(),
                                           r.boxes.cls.cpu().numpy(),
                                           r.boxes.conf.cpu().numpy(), strict=True):
                rows.append((t, int(k), float(cf), a, b, c, d))
        batch.clear()
        bt.clear()

    for t, view in frames(Path(video), fps):
        batch.append(view)
        bt.append(t)
        if len(batch) == 32:
            flush()
    if batch:
        flush()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_p, np.array(rows, np.float64).reshape(-1, 7))
    return out


def replay(face_npz: Path, det_npy: Path, conf: dict[str, float], rcfg) -> dict[str, list]:
    """-> {behaviour: [(start, end), ...]} alert intervals."""
    fz = np.load(face_npz)
    dets = np.load(det_npy)
    by_t: dict[float, list] = {}
    for t, k, cf, a, b, c, d in dets:
        if cf >= conf[NAMES[int(k)]]:
            by_t.setdefault(round(float(t), 4), []).append(
                Detection(NAMES[int(k)], float(cf), Box(float(a), float(b), float(c), float(d))))
    rules = SimpleRules(rcfg.simple)
    events: dict[str, list] = {"phone": [], "drinking": [], "eating": []}
    open_: dict[str, float] = {}
    t = 0.0
    for t, ok, lm in zip(fz["t"], fz["ok"], fz["lm"], strict=True):
        face = FaceObservation(lm.astype(np.float64), None, None, None, "none", None,
                               "geometric", 0.0) if ok else None
        out = rules.update(float(t), face, by_t.get(round(float(t), 4), []))
        for b, st in out.items():
            if st["level"] == "alert" and b not in open_:
                open_[b] = float(t)
            elif st["level"] != "alert" and b in open_:
                events[b].append((open_.pop(b), float(t)))
    for b, s in open_.items():
        events[b].append((s, float(t)))
    return events


def score(segs: list[D.Segment], events_by_video: dict, slack: float = 1.0) -> dict:
    """Per driver counts, so the bootstrap can resample drivers."""
    per_driver: dict[str, dict] = {}
    for s in segs:
        pd = per_driver.setdefault(s.driver, {"rows": {r: [0, 0, []] for r in ROWS},
                                              "fa": {"phone": 0, "drinking": 0, "eating": 0},
                                              "neg_s": 0.0})
        ev = events_by_video.get(str(s.video), {})
        if s.label in ROWS:
            alerts = ev.get(ROWS[s.label], [])
            hit = [e for e in alerts if e[0] < s.end_s + slack and e[1] > s.start_s - slack]
            pd["rows"][s.label][1] += 1
            if hit:
                pd["rows"][s.label][0] += 1
                pd["rows"][s.label][2].append(max(0.0, min(e[0] for e in hit) - s.start_s))
        elif is_negative(s.label):
            pd["neg_s"] += s.end_s - s.start_s
    # false alarms: alert starts inside a negative segment, overlaps no positive segment
    for video, ev in events_by_video.items():
        vsegs = [s for s in segs if str(s.video) == video]
        if not vsegs:
            continue
        pd = per_driver[vsegs[0].driver]
        for b, alerts in ev.items():
            pos = [s for s in vsegs if ROWS.get(s.label) == b]
            neg = [s for s in vsegs if is_negative(s.label)]
            for a0, a1 in alerts:
                if any(a0 < s.end_s + slack and a1 > s.start_s - slack for s in pos):
                    continue
                if any(s.start_s <= a0 < s.end_s for s in neg):
                    pd["fa"][b] += 1
    return per_driver


def summarise(per_driver: dict, n_boot: int = 1000, seed: int = 0) -> dict:
    drivers = sorted(per_driver)

    def agg(ds):
        out = {}
        neg_h = sum(per_driver[d]["neg_s"] for d in ds) / 3600
        for r in ROWS:
            hit = sum(per_driver[d]["rows"][r][0] for d in ds)
            n = sum(per_driver[d]["rows"][r][1] for d in ds)
            tta = [x for d in ds for x in per_driver[d]["rows"][r][2]]
            fa = sum(per_driver[d]["fa"][ROWS[r]] for d in ds)
            out[r] = {"recall": hit / n if n else None, "segments": n,
                      "fa_per_h": fa / neg_h if neg_h else None, "false_alarms": fa,
                      "tta_median_s": float(np.median(tta)) if tta else None}
        out["_neg_hours"] = neg_h
        return out

    point = agg(drivers)
    rng = random.Random(seed)
    boots = [agg([rng.choice(drivers) for _ in drivers]) for _ in range(n_boot)]
    for r in ROWS:
        for k in ("recall", "fa_per_h", "tta_median_s"):
            v = [b[r][k] for b in boots if b[r][k] is not None]
            point[r][k + "_range"] = [float(np.percentile(v, 5)), float(np.percentile(v, 95))] \
                if v else None
    point["_drivers"] = drivers
    return point


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--src", default="D:/rtdms-data/public/syndd/A1")
    p.add_argument("--split-file", default=str(ROOT / "configs" / "syndd_split.json"))
    p.add_argument("--split", default="test")
    p.add_argument("--models", nargs="+", required=True, help="name=weights.pt[@imgsz]")
    p.add_argument("--fps", type=float, default=10.0, help="frames per second (Pi-like 10)")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--cache", default="D:/rtdms-data/eval_cache")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out", required=True)
    p.add_argument("--drivers", help="comma list (smoke test)")
    args = p.parse_args()

    split = json.loads(Path(args.split_file).read_text(encoding="utf8"))
    segs = [s for s in D.syndd(args.src) if split.get(s.driver) == args.split]
    if args.drivers:
        segs = [s for s in segs if s.driver in set(args.drivers.split(","))]
    videos = sorted({str(s.video) for s in segs})
    cache = Path(args.cache)
    tag = f"fps{args.fps:g}"
    print(f"{len(videos)} videos, {len({s.driver for s in segs})} drivers ({args.split})",
          flush=True)
    faces = {v: str(cache / "faces" / tag / f"{Path(v).stem}.npz") for v in videos}
    with ProcessPoolExecutor(args.workers) as ex:
        list(ex.map(face_pass, videos, [args.fps] * len(videos), [faces[v] for v in videos]))
    print("faces cached", flush=True)

    rcfg = load_rules_config()
    rcfg.mode = "simple"
    conf = dict.fromkeys(NAMES, args.conf)
    results = {}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for spec in args.models:
        name, w = spec.split("=", 1)
        w, _, sz = w.partition("@")
        imgsz = int(sz) if sz else 416
        dets = {v: str(cache / "dets" / f"{name}_{imgsz}" / tag / f"{Path(v).stem}.npy")
                for v in videos}
        with ProcessPoolExecutor(min(args.workers, 3)) as ex:
            list(ex.map(det_pass, videos, [args.fps] * len(videos), [w] * len(videos),
                        [imgsz] * len(videos), [dets[v] for v in videos]))
        events = {v: replay(Path(faces[v]), Path(dets[v]), conf, rcfg) for v in videos}
        res = summarise(score(segs, events))
        results[name] = res
        (out / f"{name}.json").write_text(json.dumps(res, indent=1), encoding="utf8")
        print(f"\n== {name} ({args.split}, {res['_neg_hours']:.2f} h negative time)")
        for r in ROWS:
            x = res[r]
            rr = x["recall_range"] or [0, 0]
            fr = x["fa_per_h_range"] or [0, 0]
            print(f"  {r:16s} recall {x['recall'] or 0:5.2f} [{rr[0]:.2f}-{rr[1]:.2f}]  "
                  f"FA/h {x['fa_per_h'] or 0:5.1f} [{fr[0]:.1f}-{fr[1]:.1f}]  "
                  f"TTA {x['tta_median_s'] if x['tta_median_s'] is not None else '-'} s  "
                  f"(n={x['segments']})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
