#!/usr/bin/env python3
"""Live test on a laptop webcam (until the Pi camera arrives).

    python scripts/live.py --profile laptop_webcam
    python scripts/live.py --profile laptop_webcam --guided            # scored prompt sequence
    python scripts/live.py --profile laptop_webcam --fps-cap 10        # mimic Pi speed

Keys:  q quit   r redo head-pose baseline   g grayscale on/off   m next detector model
       [ / ] lower / raise detector confidence   d debug overlay on/off
       p pose wrist evidence on/off   c ear + mouth crop classifiers on/off

Startup side check (profile live.side_check): touch your RIGHT ear with your RIGHT hand for a
few seconds; if the hand lands on landmark 454 instead of 234 the webcam image is mirrored and
the flip is corrected automatically.

Privacy: nothing is written except the event log (logs/, events only) and, with --guided, the
summary in reports/. --save additionally writes the raw video + a record.py-style sidecar to
data/recordings/ (so it can be replayed with eval_events.py ours).
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rtdms_distraction.capture import WebcamSource  # noqa: E402
from rtdms_distraction.config import (  # noqa: E402
    BEHAVIOURS,
    LiveModel,
    load_pipeline_config,
    load_rules_config,
    resolve_path,
)
from rtdms_distraction.detector import make_detector  # noqa: E402
from rtdms_distraction.eventlog import EventLog  # noqa: E402
from rtdms_distraction.pipeline import DistractionPipeline  # noqa: E402
from rtdms_distraction.rules import EAR_VARIANTS  # noqa: E402
from rtdms_distraction.viz import render  # noqa: E402

# Same order as record.py --guided, with the hand-at-ear negatives split out. Ear segments are
# 12 s so the 3 s hand dwell has room. (start_s, end_s, label, prompt). 'neg_*' and 'normal'
# segments expect NO alert.
GUIDED_LIVE = [
    (0, 12, "normal", "Look at the screen normally (baseline)"),
    (12, 24, "phone_right_ear", "Phone call at your RIGHT ear (keep it there)"),
    (24, 29, "normal", "Phone down, look normally"),
    (29, 41, "phone_left_ear", "Phone call at your LEFT ear (keep it there)"),
    (41, 46, "normal", "Phone down"),
    (46, 56, "phone_in_hand", "Hold the phone LOW and text / look at it"),
    (56, 61, "normal", "Phone down, pick up a cup or bottle"),
    (61, 71, "drinking", "DRINK from the cup / bottle (2-3 sips)"),
    (71, 76, "normal", "Cup down, pick up some food"),
    (76, 88, "eating", "EAT and chew (lips closed)"),
    (88, 93, "normal", "Food down"),
    (93, 103, "neg_talking", "TALK out loud (no food)"),
    (103, 113, "neg_scratch", "SCRATCH near your ears / cheek, short (1-2 s), a few times"),
    (113, 121, "neg_hand_on_chin", "Rest your hand on your CHIN"),
    (121, 133, "neg_hand_on_head", "LEFT elbow on the desk, hand resting on your head / temple"),
    (133, 138, "normal", "Normal, eyes on the screen"),
]
EAR_BEHAVIOURS = ("phone_right_ear", "phone_left_ear")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--profile", default="laptop_webcam")
    p.add_argument("--camera-index", type=int, default=0)
    p.add_argument("--fps-cap", type=float, help="override live.fps_cap")
    p.add_argument("--no-side-check", action="store_true")
    p.add_argument("--guided", action="store_true", help="prompt sequence + scored summary")
    p.add_argument("--save", action="store_true", help="also write the raw video (privacy: off)")
    p.add_argument("--duration", type=float, help="stop after N seconds (free mode)")
    return p.parse_args()


# --------------------------------------------------------------------------- models


def discover_models(listed: list[LiveModel]) -> list[LiveModel]:
    """Profile models whose weights exist, then any other models/*_ncnn_model folder."""
    out = []
    for m in listed:
        if resolve_path(m.weights).exists():
            out.append(m)
        else:
            print(f"[live] skip model '{m.name}': {m.weights} not found")
    known = {resolve_path(m.weights) for m in out}
    for d in sorted((ROOT / "models").glob("*_ncnn_model")):
        if d.resolve() in known or not (d / "metadata.yaml").is_file():
            continue
        meta = yaml.safe_load((d / "metadata.yaml").read_text(encoding="utf8"))
        if meta.get("task", "detect") != "detect":
            continue  # pose / classifier exports are not detectors
        names = meta.get("names", {})
        names = list(names.values()) if isinstance(names, dict) else list(names)
        imgsz = meta.get("imgsz", [416])
        out.append(LiveModel(name=d.name.removesuffix("_ncnn_model"), weights=str(d),
                             imgsz=int(imgsz[0] if isinstance(imgsz, list) else imgsz),
                             hands="detector" if "hand" in names else "mediapipe"))
    return out


def ear_lines(res) -> list[str]:
    """One overlay line per ear: hand-box hit, pose wrist hit, classifier P(phone), dwell."""
    out = []
    for b, tag in (("phone_right_ear", "R ear"), ("phone_left_ear", "L ear")):
        st = res.behaviours.get(b, {})
        if "hand_s" not in st:
            continue
        mark = {True: "+", False: "-", None: "."}
        clf = "-" if st.get("clf_p") is None else f"{st['clf_p']:.2f}"
        out.append(f"{tag}: box{mark[st.get('hand_box')]} pose{mark[st.get('pose')]} "
                   f"clf {clf}  hand {st['hand_s']:.1f}s")
    if res.mouth:
        out.append("mouth: " + "  ".join(f"{k} {v:.2f}" for k, v in res.mouth.items()))
    return out


def build_detector(base_cfg, m: LiveModel, conf: float):
    cfg = copy.deepcopy(base_cfg)
    cfg.weights, cfg.backend, cfg.imgsz = m.weights, m.backend, m.imgsz
    det = make_detector(cfg)
    det.set_conf(conf)
    return det


# --------------------------------------------------------------------------- side check


def side_check(src: WebcamSource, pipe: DistractionPipeline, seconds: float) -> None:
    """Touch your RIGHT ear: is the hand nearer landmark 234 (driver's right) or 454?"""
    from rtdms_distraction.config import HandsConfig
    from rtdms_distraction.hands import MediaPipeHands

    hands = MediaPipeHands(HandsConfig(model_path=pipe.pcfg.hands.model_path))
    votes = {234: 0, 454: 0}
    t_end = time.monotonic() + seconds
    while time.monotonic() < t_end:
        frame, t = src.read()
        if frame is None:
            continue
        res = pipe.process(frame, t)
        rgb = cv2.cvtColor(res.view, cv2.COLOR_GRAY2RGB if res.view.ndim == 2
                           else cv2.COLOR_BGR2RGB)
        if res.face is not None:
            lm, fw = res.face.landmarks, res.face.face_width
            for h in hands.detect(rgb, t):
                c = np.array([h.box.cx, h.box.cy])
                d = {k: float(np.linalg.norm(c - lm[k])) for k in votes}
                k = min(d, key=d.get)
                if d[k] < 1.2 * fw:
                    votes[k] += 1
        img = render(res, banner=f"SIDE CHECK: touch your RIGHT ear with your RIGHT hand "
                                 f"({t_end - time.monotonic():.0f}s)")
        cv2.imshow("rtdms live", img)
        cv2.waitKey(1)
    hands.close()
    total = votes[234] + votes[454]
    if total < 5:
        print(f"[live] side check inconclusive ({total} hand-at-ear frames); flip stays "
              f"{src.flip}. Restart and keep the hand at the ear if the sides look swapped.")
    elif votes[454] > 0.7 * total:
        src.flip = not src.flip
        print(f"[live] side check: hand landed on landmark 454 in {votes[454]}/{total} frames "
              f"-> image is mirrored; flip_horizontal set to {src.flip}")
    elif votes[234] > 0.7 * total:
        print(f"[live] side check OK: right hand at landmark 234 (driver's right) in "
              f"{votes[234]}/{total} frames; flip_horizontal={src.flip}")
    else:
        print(f"[live] side check ambiguous (234: {votes[234]}, 454: {votes[454]}); "
              f"flip stays {src.flip}")
    pipe.reset_baseline()


# --------------------------------------------------------------------------- scoring


class GuidedScorer:
    """Per segment, for the reported setup: hit rate (share of frames with the expected
    behaviour active), raw rate (share with this frame's evidence true), alerts raised
    (behaviour onsets), false alarms (onsets of anything not expected), time-to-alert.

    Per hand-at-ear setup (hands / hands+pose / hands+pose+clf), all scored on the same frames:
    phone-at-ear hit rate and time-to-alert in the ear segments, and phone-at-ear onsets (false
    alarms) in every other segment."""

    def __init__(self, script):
        self.script = script
        self.segs = [{"start": a, "end": b, "label": lab, "prompt": pr, "frames": 0, "hit": 0,
                      "raw": 0, "onsets": [], "tta_s": None, "models": set(),
                      "v_hit": dict.fromkeys(EAR_VARIANTS, 0),
                      "v_tta": dict.fromkeys(EAR_VARIANTS),
                      "v_fa": {v: [] for v in EAR_VARIANTS}}
                     for a, b, lab, pr in script]
        self._prev = dict.fromkeys(BEHAVIOURS, "none")
        self._vprev = {v: dict.fromkeys(EAR_BEHAVIOURS, "none") for v in EAR_VARIANTS}

    def seg_at(self, t):
        return next((s for s in self.segs if s["start"] <= t < s["end"]), None)

    def update(self, t, res, model_name):
        seg = self.seg_at(t)
        onsets = [b for b, st in res.behaviours.items()
                  if st["level"] != "none" and self._prev[b] == "none"]
        self._prev = {b: st["level"] for b, st in res.behaviours.items()}
        v_onsets = {}
        for v in EAR_VARIANTS:
            lv = res.ear_levels.get(v, {})
            v_onsets[v] = [b for b in EAR_BEHAVIOURS
                           if lv.get(b, "none") != "none" and self._vprev[v][b] == "none"]
            self._vprev[v] = {b: lv.get(b, "none") for b in EAR_BEHAVIOURS}
        if seg is None:
            return
        seg["frames"] += 1
        seg["models"].add(model_name)
        exp = seg["label"] if seg["label"] in BEHAVIOURS else None
        if exp:
            st = res.behaviours[exp]
            if st["level"] != "none":
                seg["hit"] += 1
                if seg["tta_s"] is None:
                    seg["tta_s"] = round(t - seg["start"], 2)
            seg["raw"] += st["raw"] is True
        for b in onsets:
            seg["onsets"].append({"t": round(t - seg["start"], 2), "behaviour": b,
                                  "level": res.behaviours[b]["level"], "expected": b == exp})
        for v in EAR_VARIANTS:
            if exp in EAR_BEHAVIOURS and res.ear_levels.get(v, {}).get(exp, "none") != "none":
                seg["v_hit"][v] += 1
                if seg["v_tta"][v] is None:
                    seg["v_tta"][v] = round(t - seg["start"], 2)
            seg["v_fa"][v] += [b for b in v_onsets[v] if b != exp]

    def summary(self):
        rows = []
        for s in self.segs:
            exp = s["label"] in BEHAVIOURS
            n = max(1, s["frames"])
            fa = [o for o in s["onsets"] if not o["expected"]]
            row = {
                "segment": s["label"], "start_s": s["start"], "end_s": s["end"],
                "frames": s["frames"],
                "hit_rate": round(s["hit"] / n, 3) if exp else None,
                "raw_rate": round(s["raw"] / n, 3) if exp else None,
                "alerts_raised": len(s["onsets"]),
                "false_alarms": len(fa), "false_alarm_behaviours": sorted({o["behaviour"]
                                                                           for o in fa}),
                "time_to_alert_s": s["tta_s"], "models": sorted(s["models"]),
                "setups": {v: {
                    "ear_hit_rate": round(s["v_hit"][v] / n, 3)
                    if s["label"] in EAR_BEHAVIOURS else None,
                    "ear_time_to_alert_s": s["v_tta"][v],
                    "ear_false_alarms": len(s["v_fa"][v])} for v in EAR_VARIANTS},
            }
            rows.append(row)
        return rows


def write_reports(rows, meta) -> Path:
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    stem = out / f"live_{meta['utc']}"
    stem.with_suffix(".json").write_text(json.dumps({"meta": meta, "segments": rows}, indent=2),
                                         encoding="utf8", newline="\n")
    lines = [f"# Live webcam test {meta['utc']}", "",
             f"model(s): {', '.join(meta['models_used'])} | conf {meta['conf_final']} | "
             f"gray {meta['grayscale_final']} | flip {meta['flip']} | "
             f"fps cap {meta['fps_cap']} | measured {meta['measured_fps']} fps | "
             f"reported setup {meta.get('setup', '-')}", "",
             "| segment | hit rate | raw rate | alerts | false alarms | time-to-alert s |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        if r["segment"] == "normal":
            continue
        fa = f"{r['false_alarms']} {','.join(r['false_alarm_behaviours'])}".strip()
        lines.append(f"| {r['segment']} | {_p(r['hit_rate'])} | {_p(r['raw_rate'])} | "
                     f"{r['alerts_raised']} | {fa} | {r['time_to_alert_s'] or '-'} |")
    normal_fa = sum(r["false_alarms"] for r in rows if r["segment"] == "normal")
    lines += ["", f"False alarms during the 'normal' gaps: {normal_fa}", ""]
    if rows and "setups" in rows[0]:
        by = {r["segment"]: r for r in rows}

        def fa(seg, v):
            return str(by[seg]["setups"][v]["ear_false_alarms"]) if seg in by else "-"

        lines += ["## Phone at ear: hand-at-ear setups (same frames)", "",
                  "| setup | R-ear hit | R-ear TTA s | L-ear hit | L-ear TTA s | "
                  "FA scratch | FA hand on chin | FA elbow-on-head | FA talking | FA normal |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for v in EAR_VARIANTS:
            r_ = by.get("phone_right_ear", {}).get("setups", {}).get(v, {})
            l_ = by.get("phone_left_ear", {}).get("setups", {}).get(v, {})
            fa_norm = sum(r["setups"][v]["ear_false_alarms"] for r in rows
                          if r["segment"] == "normal")
            lines.append(
                f"| {v} | {_p(r_.get('ear_hit_rate'))} | {r_.get('ear_time_to_alert_s') or '-'} "
                f"| {_p(l_.get('ear_hit_rate'))} | {l_.get('ear_time_to_alert_s') or '-'} | "
                f"{fa('neg_scratch', v)} | {fa('neg_hand_on_chin', v)} | "
                f"{fa('neg_hand_on_head', v)} | {fa('neg_talking', v)} | {fa_norm} |")
        if not meta.get("classifier_loaded"):
            lines += ["", "hands+pose+clf = hands+pose here: no ear-crop classifier was loaded."]
        lines.append("")
    lines += ["hit rate = share of frames with the expected behaviour active (after smoothing);",
              "raw rate = share of frames whose evidence fired before smoothing;",
              "FA = phone-at-ear onsets in that segment (scratching must stay under the 3 s "
              "dwell)."]
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf8", newline="\n")
    return stem


def _p(v):
    return "-" if v is None else f"{v:.0%}"


# --------------------------------------------------------------------------- main


def main() -> int:
    args = parse_args()
    pcfg = load_pipeline_config(profile=args.profile)
    rcfg = load_rules_config()
    live = pcfg.live
    fps_cap = args.fps_cap if args.fps_cap is not None else live.fps_cap
    c = pcfg.capture

    src = WebcamSource(args.camera_index, c.width, c.height, c.fps, c.flip_horizontal,
                       backend=c.backend, gray=False).start()
    gray = c.grayscale
    models = discover_models(live.models) or [LiveModel("config", pcfg.detector.weights,
                                                        pcfg.detector.backend,
                                                        pcfg.detector.imgsz,
                                                        pcfg.hands.source)]
    mi = 0
    conf = min(pcfg.detector.conf.values()) if pcfg.detector.conf else 0.25
    pcfg.hands.source = models[0].hands
    det = build_detector(pcfg.detector, models[0], conf)
    pipe = DistractionPipeline(pcfg, rcfg, src.size, detector=det)
    log = EventLog(resolve_path(pcfg.eventlog.dir), per_frame=False, tag="live")
    debug = True

    def announce(why):
        m = models[mi]
        print(f"[live] {why}: model={m.name} ({m.weights}, imgsz {m.imgsz}, hands {m.hands}) "
              f"conf={conf:.2f} gray={gray} flip={src.flip} fps_cap={fps_cap} "
              f"ear_setup={pipe.variant} (pose {'on' if pipe.pose_on else 'off'}"
              f"{'' if pipe.pose else ' [not loaded]'}, classifier "
              f"{'on' if pipe.clf_on else 'off'}{'' if pipe.ear_clf else ' [not loaded]'})",
              flush=True)

    print(f"[live] {src.describe()} -> view {pipe.roi.out_w}x{pipe.roi.out_h}; "
          f"{len(models)} model(s): {', '.join(m.name for m in models)}")
    announce("start")
    log.session(source=src.describe(), profile=args.profile, model=models[mi].name, conf=conf,
                gray=gray, fps_cap=fps_cap)

    if live.side_check and not args.no_side_check:
        side_check(src, pipe, live.side_check_s)
        announce("after side check")

    scorer = GuidedScorer(GUIDED_LIVE) if args.guided else None
    utc = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    writer = None
    raw_path = ROOT / "data" / "recordings" / f"live_{utc}.mp4"
    models_used = {models[mi].name}
    t0 = time.monotonic()
    pipe.reset_baseline()
    n, fps, fps_t0, last = 0, 0.0, time.perf_counter(), 0.0
    try:
        while True:
            if fps_cap:
                wait = 1.0 / fps_cap - (time.monotonic() - last)
                if wait > 0:
                    time.sleep(wait)
            last = time.monotonic()
            frame, t = src.read()
            if frame is None:
                continue
            tr = t - t0
            if scorer and tr >= GUIDED_LIVE[-1][1]:
                break
            if args.duration and tr >= args.duration:
                break
            if args.save:
                if writer is None:
                    raw_path.parent.mkdir(parents=True, exist_ok=True)
                    writer = cv2.VideoWriter(str(raw_path), cv2.VideoWriter_fourcc(*"mp4v"),
                                             fps_cap or c.fps, (frame.shape[1], frame.shape[0]))
                writer.write(frame)
            res = pipe.process(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if gray else frame, tr)
            n += 1
            if n % 15 == 0:
                now = time.perf_counter()
                fps, fps_t0 = 15 / (now - fps_t0), now
            for e in log.update(tr, res.behaviours):
                print(f"[event] t={e['t']:.1f} {e['event']} {e['behaviour']} "
                      f"{e.get('level', e.get('peak_level', ''))}", flush=True)
            banner = None
            if scorer:
                scorer.update(tr, res, models[mi].name)
                seg = scorer.seg_at(tr)
                if seg:
                    banner = f"{seg['prompt']}  ({seg['end'] - tr:.0f}s)"
            m = models[mi]
            info = [f"model {m.name} @{m.imgsz}  hands {m.hands}",
                    f"conf {conf:.2f}  gray {'on' if gray else 'off'}  flip "
                    f"{'on' if src.flip else 'off'}  cap {fps_cap or '-'}",
                    f"ear setup {pipe.variant}",
                    *ear_lines(res),
                    "q r g m [ ] d p c"]
            cv2.imshow("rtdms live", render(res, fps, rcfg.phone_in_hand.holder_zones,
                                            debug=debug, info=info, banner=banner))
            k = cv2.waitKey(1) & 0xFF
            if k in (27, ord("q")):
                break
            if k == ord("r"):
                pipe.reset_baseline()
                print("[live] head-pose baseline restarted (sit normally ~10 s)", flush=True)
            elif k == ord("g"):
                gray = not gray
                announce("grayscale toggled")
            elif k == ord("d"):
                debug = not debug
            elif k == ord("p") and pipe.pose is not None:
                pipe.pose_on = not pipe.pose_on
                announce("pose toggled")
            elif k == ord("c") and (pipe.ear_clf is not None or pipe.mouth_clf is not None):
                pipe.clf_on = not pipe.clf_on
                announce("ear classifier toggled")
            elif k == ord("m") and len(models) > 1:
                mi = (mi + 1) % len(models)
                pipe.set_detector(build_detector(pcfg.detector, models[mi], conf), models[mi].hands)
                models_used.add(models[mi].name)
                announce("model switched")
            elif k in (ord("["), ord("]")):
                conf = float(np.clip(conf + (live.conf_step if k == ord("]") else
                                             -live.conf_step), 0.05, 0.9))
                pipe.detector.set_conf(conf)
                announce("confidence changed")
    except KeyboardInterrupt:
        pass
    finally:
        elapsed = time.monotonic() - t0
        log.close(time.monotonic() - t0)
        src.stop()
        pipe.close()
        cv2.destroyAllWindows()
        if writer is not None:
            writer.release()
            side = {"subject": "live", "scenario": "live_guided" if scorer else "live",
                    "lighting": "day", "utc": utc, "frames": n, "seconds": round(elapsed, 2),
                    "measured_fps": round(n / elapsed, 2) if elapsed else None,
                    "source": src.describe(), "notes": "scripts/live.py --save",
                    "timeline": [{"start": a, "end": b, "label": lab}
                                 for a, b, lab, _ in GUIDED_LIVE] if scorer else []}
            raw_path.with_suffix(".json").write_text(json.dumps(side, indent=2),
                                                     encoding="utf8", newline="\n")
            print(f"[live] raw video saved: {raw_path}")
    print(f"[live] {n} frames, {n / max(1e-6, elapsed):.1f} fps processed; events: {log.path}")
    if scorer:
        meta = {"utc": utc, "profile": args.profile, "models_used": sorted(models_used),
                "conf_final": round(conf, 2), "grayscale_final": gray, "flip": src.flip,
                "fps_cap": fps_cap, "measured_fps": round(n / max(1e-6, elapsed), 1),
                "frames": n, "source": src.describe(), "setup": pipe.variant,
                "pose_loaded": pipe.pose is not None,
                "classifier_loaded": pipe.ear_clf is not None,
                "mouth_classifier_loaded": pipe.mouth_clf is not None}
        stem = write_reports(scorer.summary(), meta)
        print(f"[live] summary: {stem.with_suffix('.md')}")
        print(stem.with_suffix(".md").read_text(encoding="utf8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
