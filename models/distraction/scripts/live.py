#!/usr/bin/env python3
"""Live test on a laptop webcam (until the Pi camera arrives).

    python scripts/live.py                                             # simple mode (default)
    python scripts/live.py --mode full                                 # rule engine (hands, pose)
    python scripts/live.py --profile laptop_webcam --guided            # scored prompt sequence
    python scripts/live.py --profile laptop_webcam --fps-cap 10        # mimic Pi speed

Simple mode: one phone / drink / food detector; phone box >= 1 s -> phone ALERT, drink / food
box over the lower face -> drinking / eating ALERT. Keys r / p / c only matter in full mode.

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
from rtdms_distraction.rules import CLF_VARIANT, EAR_VARIANTS  # noqa: E402
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
    p.add_argument("--mode", choices=["simple", "full"], default="simple",
                   help="simple = detector + 3 rules (phone >= 1 s, drink / food at the lower "
                        "face); full = rule engine with hands, pose, crop classifiers "
                        "(--guided always uses full)")
    p.add_argument("--camera-index", type=int, default=0)
    p.add_argument("--fps-cap", type=float, help="override live.fps_cap")
    p.add_argument("--no-side-check", action="store_true")
    p.add_argument("--guided", action="store_true", help="prompt sequence + scored summary")
    p.add_argument("--save", action="store_true", help="also write the raw video (privacy: off)")
    p.add_argument("--duration", type=float, help="stop after N seconds (free mode)")
    p.add_argument("--compare-ear", nargs="*", default=["models/ear_cls_128_ncnn_model"],
                   help="--guided: extra ear classifiers scored side by side on the same frames")
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


def model_name(weights: str) -> str:
    return Path(weights).name.removesuffix("_ncnn_model")


def model_imgsz(d: Path, default: int) -> int:
    meta = d / "metadata.yaml"
    if not meta.is_file():
        return default
    v = yaml.safe_load(meta.read_text(encoding="utf8")).get("imgsz", default)
    return int(v[0] if isinstance(v, list) else v)


def lock_text(pipe) -> str:
    lock = getattr(pipe.facemesh, "lock", None)
    if lock is None:
        return "driver lock off"
    return f"driver locked ({lock.size:.0f} px face)" if lock.locked else "driver lock: searching"


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


def build_detector(base_cfg, m: LiveModel, conf: float | None):
    """conf None keeps the profile's per-class thresholds (phone / drink / food may differ);
    a number (set with [ / ]) applies one threshold to every class."""
    cfg = copy.deepcopy(base_cfg)
    cfg.weights, cfg.backend, cfg.imgsz = m.weights, m.backend, m.imgsz
    det = make_detector(cfg)
    if conf is not None:
        det.set_conf(conf)
    return det


# --------------------------------------------------------------------------- side check


def side_check(src: WebcamSource, pipe: DistractionPipeline, seconds: float) -> None:
    """Touch your RIGHT ear: is the hand nearer landmark 234 (driver's right) or 454?"""
    from rtdms_distraction.config import HandsConfig
    from rtdms_distraction.hands import MediaPipeHands

    try:
        hands = MediaPipeHands(HandsConfig(model_path=pipe.pcfg.hands.model_path))
    except FileNotFoundError:
        print("[live] side check skipped: hand_landmarker.task missing "
              "(python scripts/fetch_models.py)", flush=True)
        return
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

    Per hand-at-ear setup (hands / hands+pose / hands+pose+clf, plus one per extra ear
    classifier), all scored on the same frames: phone-at-ear hit rate, ALERT rate and
    time-to-alert in the ear segments; phone-at-ear onsets (false alarms) and ALERT onsets
    (false alerts) in every other segment. The classifier setups share the hand evidence, so
    their WARNINGs are identical; they differ only in ALERT (phone seen during the episode).

    Per ear classifier (ear_models: [(label, None = res.clf | name in res.clf_alt)]): share of
    frames with P(phone) >= thr at the expected ear (ear segments) or at either ear."""

    def __init__(self, script, variants=EAR_VARIANTS, ear_models=(), thr=0.6):
        self.script, self.variants, self.ear_models, self.thr = script, list(variants), \
            list(ear_models), thr
        self.segs = [{"start": a, "end": b, "label": lab, "prompt": pr, "frames": 0, "hit": 0,
                      "raw": 0, "onsets": [], "tta_s": None, "models": set(),
                      "v_hit": dict.fromkeys(self.variants, 0),
                      "v_alert": dict.fromkeys(self.variants, 0),
                      "v_tta": dict.fromkeys(self.variants),
                      "v_fa": {v: [] for v in self.variants},
                      "v_fa_alert": {v: [] for v in self.variants},
                      "m_n": {m: 0 for m, _ in self.ear_models},
                      "m_phone": {m: 0 for m, _ in self.ear_models}}
                     for a, b, lab, pr in script]
        self._prev = dict.fromkeys(BEHAVIOURS, "none")
        self._vprev = {v: dict.fromkeys(EAR_BEHAVIOURS, "none") for v in self.variants}

    def seg_at(self, t):
        return next((s for s in self.segs if s["start"] <= t < s["end"]), None)

    def update(self, t, res, model_name):
        seg = self.seg_at(t)
        onsets = [b for b, st in res.behaviours.items()
                  if st["level"] != "none" and self._prev[b] == "none"]
        self._prev = {b: st["level"] for b, st in res.behaviours.items()}
        v_onsets, v_alerts = {}, {}
        for v in self.variants:
            lv, pv = res.ear_levels.get(v, {}), self._vprev[v]
            v_onsets[v] = [b for b in EAR_BEHAVIOURS
                           if lv.get(b, "none") != "none" and pv[b] == "none"]
            v_alerts[v] = [b for b in EAR_BEHAVIOURS
                           if lv.get(b, "none") == "alert" and pv[b] != "alert"]
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
        for v in self.variants:
            lv = res.ear_levels.get(v, {}).get(exp, "none") if exp in EAR_BEHAVIOURS else "none"
            if lv != "none":
                seg["v_hit"][v] += 1
                if seg["v_tta"][v] is None:
                    seg["v_tta"][v] = round(t - seg["start"], 2)
            seg["v_alert"][v] += lv == "alert"
            seg["v_fa"][v] += [b for b in v_onsets[v] if b != exp]
            seg["v_fa_alert"][v] += [b for b in v_alerts[v] if b != exp]
        for m, key in self.ear_models:
            p = res.clf if key is None else res.clf_alt.get(key)
            if not p:
                continue
            seg["m_n"][m] += 1
            ears = [exp] if exp in EAR_BEHAVIOURS else list(EAR_BEHAVIOURS)
            seg["m_phone"][m] += any(p.get(b, 0.0) >= self.thr for b in ears)

    def summary(self):
        rows = []
        for s in self.segs:
            exp = s["label"] in BEHAVIOURS
            ear = s["label"] in EAR_BEHAVIOURS
            n = max(1, s["frames"])
            fa = [o for o in s["onsets"] if not o["expected"]]
            rows.append({
                "segment": s["label"], "start_s": s["start"], "end_s": s["end"],
                "frames": s["frames"],
                "hit_rate": round(s["hit"] / n, 3) if exp else None,
                "raw_rate": round(s["raw"] / n, 3) if exp else None,
                "alerts_raised": len(s["onsets"]),
                "false_alarms": len(fa), "false_alarm_behaviours": sorted({o["behaviour"]
                                                                           for o in fa}),
                "time_to_alert_s": s["tta_s"], "models": sorted(s["models"]),
                "setups": {v: {
                    "ear_hit_rate": round(s["v_hit"][v] / n, 3) if ear else None,
                    "ear_alert_rate": round(s["v_alert"][v] / n, 3) if ear else None,
                    "ear_time_to_alert_s": s["v_tta"][v],
                    "ear_false_alarms": len(s["v_fa"][v]),
                    "ear_false_alerts": len(s["v_fa_alert"][v])} for v in self.variants},
                "ear_models": {m: {"frames": s["m_n"][m], "phone_frames": s["m_phone"][m],
                                   "phone_rate": round(s["m_phone"][m] / s["m_n"][m], 3)
                                   if s["m_n"][m] else None} for m, _ in self.ear_models},
            })
        return rows


NEG_EAR = (("neg_scratch", "scratch"), ("neg_hand_on_chin", "hand on chin"),
           ("neg_hand_on_head", "elbow-on-head"), ("neg_talking", "talking"))


def setup_label(v, meta):
    if v == CLF_VARIANT:
        return f"hands+pose+clf [{meta.get('ear_model', 'configured')}]"
    if v.startswith(CLF_VARIANT + ":"):
        return f"hands+pose+clf [{v.split(':', 1)[1]}]"
    return v


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
        lines += ear_tables(rows, meta)
    lines += ["hit rate = share of frames with the expected behaviour active (after smoothing);",
              "raw rate = share of frames whose evidence fired before smoothing."]
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf8", newline="\n")
    return stem


def ear_tables(rows, meta) -> list[str]:
    by = {r["segment"]: r for r in rows}
    variants = list(rows[0]["setups"])
    normal = [r for r in rows if r["segment"] == "normal"]

    def fa(seg, v):
        if seg not in by:
            return "-"
        s = by[seg]["setups"][v]
        return f"{s['ear_false_alarms']} ({s['ear_false_alerts']})"

    lines = ["## Phone at ear: setups and ear models (same frames)", "",
             "hit = hand-at-ear WARNING or ALERT; ALERT = phone seen during the episode (box or "
             "ear classifier). FA = phone-at-ear onsets (ALERT onsets in brackets).", "",
             "| setup | R-ear hit | R-ear ALERT | R TTA s | L-ear hit | L-ear ALERT | L TTA s | "
             + " | ".join(f"FA {n}" for _, n in NEG_EAR) + " | FA normal |",
             "|---|---|---|---|---|---|---|" + "---|" * (len(NEG_EAR) + 1)]
    for v in variants:
        r_ = by.get("phone_right_ear", {}).get("setups", {}).get(v, {})
        l_ = by.get("phone_left_ear", {}).get("setups", {}).get(v, {})
        fa_n = sum(r["setups"][v]["ear_false_alarms"] for r in normal)
        fa_na = sum(r["setups"][v]["ear_false_alerts"] for r in normal)
        lines.append(
            f"| {setup_label(v, meta)} | {_p(r_.get('ear_hit_rate'))} | "
            f"{_p(r_.get('ear_alert_rate'))} | {r_.get('ear_time_to_alert_s') or '-'} | "
            f"{_p(l_.get('ear_hit_rate'))} | {_p(l_.get('ear_alert_rate'))} | "
            f"{l_.get('ear_time_to_alert_s') or '-'} | "
            + " | ".join(fa(s, v) for s, _ in NEG_EAR) + f" | {fa_n} ({fa_na}) |")
    if not meta.get("classifier_loaded"):
        lines += ["", "hands+pose+clf = hands+pose here: no ear-crop classifier was loaded."]
    models = list(rows[0].get("ear_models", {}))
    if models:
        def rate(seg, m):
            e = by.get(seg, {}).get("ear_models", {}).get(m, {})
            return _p(e.get("phone_rate"))

        def normal_rate(m):
            n = sum(r["ear_models"][m]["frames"] for r in normal)
            return _p(sum(r["ear_models"][m]["phone_frames"] for r in normal) / n if n else None)

        lines += ["", "### Ear-crop classifiers: frames with P(phone) >= "
                  f"{meta.get('clf_threshold', 0.6)}",
                  "", "ear segments: at the expected ear; others: at either ear.", "",
                  "| ear model | R-ear seg | L-ear seg | " +
                  " | ".join(n for _, n in NEG_EAR) + " | normal |",
                  "|---|---|---|" + "---|" * (len(NEG_EAR) + 1)]
        for m in models:
            lines.append(f"| {m} | {rate('phone_right_ear', m)} | {rate('phone_left_ear', m)} | "
                         + " | ".join(rate(s, m) for s, _ in NEG_EAR) + f" | {normal_rate(m)} |")
        verdict = ear_verdict(rows, meta)
        if verdict:
            lines += ["", f"**Suggested ear model: {verdict}** (fewest false ALERTs over the "
                      "negative and normal segments; tie -> higher mean ALERT rate at the ears)."]
    return lines + [""]


def ear_verdict(rows, meta) -> str | None:
    """Among the classifier setups: fewest false ALERTs, then the highest ear ALERT rate."""
    variants = [v for v in rows[0]["setups"] if v.startswith(CLF_VARIANT)]
    if len(variants) < 2:
        return None
    by = {r["segment"]: r for r in rows}

    def key(v):
        fal = sum(r["setups"][v]["ear_false_alerts"] for r in rows
                  if r["segment"] not in EAR_BEHAVIOURS)
        alert = [by[s]["setups"][v]["ear_alert_rate"] or 0.0 for s in EAR_BEHAVIOURS if s in by]
        return (fal, -(sum(alert) / max(1, len(alert))))

    keys = {v: key(v) for v in variants}
    best = min(variants, key=keys.get)
    if sum(k == keys[best] for k in keys.values()) > 1:
        return "no difference in this run"
    return setup_label(best, meta).split("[", 1)[-1].rstrip("]")


def _p(v):
    return "-" if v is None else f"{v:.0%}"


# --------------------------------------------------------------------------- main


def main() -> int:
    args = parse_args()
    pcfg = load_pipeline_config(profile=args.profile)
    rcfg = load_rules_config()
    rcfg.mode = "full" if args.guided else args.mode  # guided scoring is built on the ear rules
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
    conf_user = False  # True once [ / ] set one threshold for every class
    pcfg.hands.source = models[0].hands
    det = build_detector(pcfg.detector, models[0], None)
    pipe = DistractionPipeline(pcfg, rcfg, src.size, detector=det)
    log = EventLog(resolve_path(pcfg.eventlog.dir), per_frame=False, tag="live")
    debug = True

    def announce(why):
        m = models[mi]
        print(f"[live] {why}: model={m.name} ({m.weights}, imgsz {m.imgsz}, hands {m.hands}) "
              f"conf={conf:.2f} gray={gray} flip={src.flip} fps_cap={fps_cap} "
              f"ear_setup={pipe.variant} (pose {'on' if pipe.pose_on else 'off'}"
              f"{'' if pipe.pose else ' [not loaded]'}, classifier "
              f"{'on' if pipe.clf_on else 'off'}{'' if pipe.ear_clf else ' [not loaded]'}) "
              f"{lock_text(pipe)}", flush=True)

    print(f"[live] {src.describe()} -> view {pipe.roi.out_w}x{pipe.roi.out_h}; "
          f"{len(models)} model(s): {', '.join(m.name for m in models)}")
    announce("start")
    log.session(source=src.describe(), profile=args.profile, model=models[mi].name, conf=conf,
                gray=gray, fps_cap=fps_cap)

    if rcfg.mode == "simple":
        print("[live] simple mode: phone box >= 1 s -> phone ALERT; drink / food box over the "
              "lower face -> drinking / eating ALERT (hands, pose, classifiers off)", flush=True)
    elif live.side_check and not args.no_side_check:
        side_check(src, pipe, live.side_check_s)
        announce("after side check")
    if getattr(pipe.facemesh, "locked", None) is False:
        print("[live] driver lock: no face locked yet; it locks onto the largest face in the "
              "driver ROI as soon as one is seen", flush=True)

    scorer, ear_models = None, []
    if args.guided:
        if pipe.ear_clf is not None:
            ear_models.append((model_name(pcfg.ear_classifier.weights), None))
        for w in args.compare_ear:
            d = resolve_path(w)
            same = d.resolve() == resolve_path(pcfg.ear_classifier.weights).resolve()
            if pipe.ear_clf is None or not (d / "model.ncnn.param").is_file() or same:
                print(f"[live] --compare-ear {w}: skipped (missing, same as the configured "
                      f"model, or no configured ear classifier)")
                continue
            cfg = copy.deepcopy(pcfg.ear_classifier)
            cfg.weights, cfg.imgsz = str(d), model_imgsz(d, cfg.imgsz)
            name = model_name(w)
            pipe.add_ear_model(name, cfg)
            ear_models.append((name, name))
            print(f"[live] comparing ear models: {[m for m, _ in ear_models]}", flush=True)
        scorer = GuidedScorer(GUIDED_LIVE, pipe.rules.variants, ear_models,
                              rcfg.hand_at_ear.classifier_phone)
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
                    f"ear setup {pipe.variant}  {lock_text(pipe)}",
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
                pipe.set_detector(build_detector(pcfg.detector, models[mi],
                                                 conf if conf_user else None), models[mi].hands)
                models_used.add(models[mi].name)
                announce("model switched")
            elif k in (ord("["), ord("]")):
                conf = float(np.clip(conf + (live.conf_step if k == ord("]") else
                                             -live.conf_step), 0.05, 0.9))
                conf_user = True
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
                "ear_model": model_name(pcfg.ear_classifier.weights),
                "ear_models_compared": [m for m, _ in ear_models],
                "clf_threshold": rcfg.hand_at_ear.classifier_phone,
                "driver_lock": pcfg.facemesh.driver_lock,
                "mouth_classifier_loaded": pipe.mouth_clf is not None}
        stem = write_reports(scorer.summary(), meta)
        print(f"[live] summary: {stem.with_suffix('.md')}")
        print(stem.with_suffix(".md").read_text(encoding="utf8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
