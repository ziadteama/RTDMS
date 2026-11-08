"""v2 hybrid evaluation: release model vs v1 (action classifier for all alerts) vs v2 (action
classifier + phone checks for call / texting, release boxes + mouth filter for drinking / eating).

Test sets: SynDD-test, 3MDAD-test (15 subjects, every action incl. fatigue AC12 / AC15),
EBDD-test (akkas, jewel), DAD front IR. Clips: SynDD segments (minus 0.5 s edges), 3MDAD action
folders, EBDD videos (minus 0.5 s edges), DAD clips / normal-driving videos.

Per system and set: clip recall per alert class, false alerts per hour on normal + hand_on_face
clips, and every false alert listed as (alert -> true class of the clip).

python evaluate_v2.py <tag> <action weights> <ear phone weights> <lap phone weights>
       [--lap-p 0.4] [--min-p-texting 0.0] [--mouth-k 1.5]   (defaults = D18 / D19)
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from alerts import CLASSES, AlertLogic  # noqa: E402
from evaluate import (EDGE, MDAD_ACT, PRED, confusion, plot_cm, predict,  # noqa: E402
                      run_clips, syndd_windows)
from evaluate import preds as preds_v1  # noqa: E402

A = Path("D:/rtdms-data/action_v1")
DATA = Path("D:/rtdms-data")
REPO = Path(r"C:\Users\youss\projects\RTDMS\models\distraction")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "experiments"))
sys.path.insert(0, str(REPO / "scripts"))
ALL_CLASSES = CLASSES + ["smoking"]
ALERTS = ("call", "texting", "drinking", "eating")
REL_KEY = {"call": "phone", "texting": "phone", "drinking": "drinking", "eating": "eating"}
OWN_KEY = {a: a for a in ALERTS}
CONF = {"phone": .40, "drink": .45, "food": .40}


# ----------------------------------------------------------------------------- our crops
def rows2(ds, split="test"):
    p = A / "data" / "v2" / f"{ds}.csv"
    rs = list(csv.DictReader(open(p, encoding="utf8"))) if p.exists() else []
    return [r for r in rs if r["split"] == split]


def act_classes(w):
    from ultralytics import YOLO
    names = set(YOLO(str(w), task="classify").names.values())
    return [c for c in ALL_CLASSES if c in names]


def preds2(tag, ds, split, act_w, ear_w, lap_w):
    f = PRED / f"{tag}_{ds}_{split}_v2.npz"
    rs = rows2(ds, split)
    classes = act_classes(act_w)
    if f.exists():
        z = np.load(f)
        if len(z["act"]) == len(rs):
            return rs, z["act"], z["ph"], z["lap"], classes
    PRED.mkdir(parents=True, exist_ok=True)
    d = A / "data"
    act = predict(act_w, [str(d / r["up"]) for r in rs], classes, 224)
    pr = predict(ear_w, [str(d / r["ear_r"]) for r in rs], ["phone_in_hand"], 128)[:, 0]
    pl = predict(ear_w, [str(d / r["ear_l"]) for r in rs], ["phone_in_hand"], 128)[:, 0]
    lap = predict(lap_w, [str(d / r["lap"]) for r in rs], ["phone_in_hand"], 128)[:, 0]
    ph = np.stack([pr, pl], 1)
    np.savez(f, act=act, ph=ph, lap=lap)
    return rs, act, ph, lap, classes


def ours_events(rs, act, ph, lap, classes, lap_p, min_p):
    """clip -> {alert: [(start, end)]} for call / texting from the action classifier."""
    by = defaultdict(list)
    for k, r in enumerate(rs):
        by[r["clip"]].append(k)
    out = {}
    for clip, ks in by.items():
        ks.sort(key=lambda k: float(rs[k]["t"]))
        lg = AlertLogic(classes=classes, alerts=("call", "texting"), lap_p=lap_p, use_talk=False,
                        min_p=min_p)
        ev, start = defaultdict(list), {}
        t = 0.0
        for k in ks:
            t = float(rs[k]["t"])
            st, _ = lg.update(t, act[k], float(ph[k].max()), float(rs[k]["lip"]), float(lap[k]))
            for a, on in st.items():
                if on and a not in start:
                    start[a] = t
                elif not on and a in start:
                    ev[a].append((start.pop(a), t))
        for a, s in start.items():
            ev[a].append((s, t))
        out[clip] = dict(ev)
    return out


# ----------------------------------------------------------------------------- release frames
def face_obs(lm):
    from rtdms_distraction.types import FaceObservation
    return FaceObservation(lm, None, None, None, "none", None, "geometric", 0.0)


def drink_eat_events(frames, mouth_k=1.5, every=1):
    """frames: [(t, lm (478, 2) array or None, [(cls, conf, x1, y1, x2, y2)])]. Release simple
    rules on drink / food boxes, after the mouth-distance filter (mouth_k=None: no filter).
    every=2: the detector runs on every 2nd frame and the other frames reuse its boxes (as the
    live pipeline's detector.every_n does); face mesh still runs every frame."""
    from rtdms_distraction.config import load_rules_config
    from rtdms_distraction.simple_rules import SimpleRules
    from rtdms_distraction.types import Box, Detection

    cfg = load_rules_config()
    cfg.simple.texting = False
    rules = SimpleRules(cfg.simple)
    ev, start, last, t = defaultdict(list), {}, None, 0.0
    last_dets = []
    for i, (t, lm, dets) in enumerate(frames):
        if i % every == 0:
            last_dets = dets
        dets = last_dets
        face = face_obs(lm) if lm is not None else None
        if lm is not None:
            last = (t, lm)
        held = last[1] if last is not None and t - last[0] <= 1.0 else None
        keep = []
        for c, cf, x1, y1, x2, y2 in dets:
            if c not in ("drink", "food") or cf < CONF[c]:
                continue
            if mouth_k is not None:
                if held is None:
                    continue
                mouth = (held[13] + held[14]) / 2
                fh = float(np.linalg.norm(held[10] - held[152]))
                if np.hypot((x1 + x2) / 2 - mouth[0], (y1 + y2) / 2 - mouth[1]) > mouth_k * fh:
                    continue
            keep.append(Detection(c, cf, Box(x1, y1, x2, y2)))
        out = rules.update(t, face, keep)
        for b in ("drinking", "eating"):
            on = out[b]["level"] == "alert"
            if on and b not in start:
                start[b] = t
            elif not on and b in start:
                ev[b].append((start.pop(b), t))
    for b, s in start.items():
        ev[b].append((s, t))
    return dict(ev)


def level_events(frames_levels):
    """[(t, {behaviour: level})] -> {behaviour: [(start, end)]} (release alerts)."""
    ev, start, t = defaultdict(list), {}, 0.0
    for t, lv in frames_levels:
        for b, level in lv.items():
            on = level == "alert"
            if on and b not in start:
                start[b] = t
            elif not on and b in start:
                ev[b].append((start.pop(b), t))
    for b, s in start.items():
        ev[b].append((s, t))
    return dict(ev)


def lm_array(d):
    arr = np.zeros((478, 2), np.float64)
    for k, v in d.items():
        arr[int(k)] = v
    return arr


def load_release_clips(ds):
    """clip -> (cls, side, s, e, frames for drink_eat_events, release events)."""
    from extract import DAD_MAP, EBDD_MAP
    out = {}
    for f in sorted((A / "runs" / "release_v2" / ds).glob("*.json")):
        c = json.loads(f.read_text(encoding="utf8"))
        fr = c["frames"]
        if not fr:
            continue
        clip = c["clip"]
        if ds == "3mdad":
            a = int(clip.split("_AC")[1])
            cls, side = MDAD_ACT[a], {7: "L", 8: "R"}.get(a, "")
        elif ds == "ebdd":
            key = next(k for k in EBDD_MAP if clip.endswith("_" + k))
            cls, side = EBDD_MAP[key], ""
        else:
            act = clip.split("_", 1)[1]
            cls, side = ("normal", "") if act.startswith("normal") else DAD_MAP[act]
        s, e = fr[0]["t"], fr[-1]["t"]
        if ds == "ebdd":
            s, e = s + EDGE, e - EDGE
        frames = [(r["t"], lm_array(r["lm"]) if r["lm"] else None,
                   [tuple(d) for d in r["dets"]]) for r in fr]
        rel = level_events([(r["t"], r["levels"]) for r in fr])
        out[clip] = (cls, side, s, e, frames, rel)
    return out


def syndd_release(win, clips):
    """SynDD: cached det_v2d boxes (conf >= .05, 10 fps) + cached faces, per video."""
    import ear_rule
    import eval_simple as E

    by_video = defaultdict(list)
    for c in clips:
        by_video[win[c][0]].append(c)
    rel, frames_by_video = {}, {}
    for stem in by_video:
        rel[stem] = ear_rule.replay(stem, 0.0, 0.0)
        fz = np.load(ear_rule.FACES / f"{stem}.npz")
        dets = np.load(ear_rule.DETS / f"{stem}.npy")
        by_t = defaultdict(list)
        for t, k, cf, a, b, c_, d in dets:
            by_t[round(float(t), 4)].append((E.NAMES[int(k)], float(cf), float(a), float(b),
                                             float(c_), float(d)))
        frames_by_video[stem] = [(float(t), lm.astype(np.float64) if ok else None,
                                  by_t.get(round(float(t), 4), []))
                                 for t, ok, lm in zip(fz["t"], fz["ok"], fz["lm"], strict=True)]
    return rel, frames_by_video


# ----------------------------------------------------------------------------- scoring
def clip_onsets(events, s, e, cls, key):
    """Alert onsets inside [s, e]; an alert already on at s counts once, for recall only."""
    ons = Counter()
    carry = set()
    for b, ivs in events.items():
        for a, z in ivs:
            if s <= a <= e:
                ons[b] += 1
            elif a < s <= z:
                carry.add(b)
    for b in carry:
        if not ons[b] and key.get(cls) == b:
            ons[b] = 1
    return dict(ons)


def summarise(cl, key):
    res, fa_list = {}, Counter()
    for c in ALERTS:
        pos = [x for x in cl if x["cls"] == c]
        if pos:
            res[f"{c}_recall"] = [sum(x["onsets"].get(key[c], 0) > 0 for x in pos), len(pos)]
    g = [x for x in cl if x["cls"] in ("normal", "hand_on_face")]
    h = sum(x["dur"] for x in g) / 3600
    n = sum(sum(x["onsets"].values()) for x in g)
    res["fa_normal_hof"] = [n, round(h, 3), round(n / h, 1) if h else None]
    for x in cl:
        for b, v in x["onsets"].items():
            right = (b == "phone" and x["cls"] in ("call", "texting")) or b == x["cls"]
            if not right:
                fa_list[f"{b} -> {x['cls']}"] += v
    res["false_alerts"] = dict(sorted(fa_list.items(), key=lambda kv: -kv[1]))
    tot_h = sum(x["dur"] for x in cl) / 3600
    res["all_false_per_h"] = round(sum(fa_list.values()) / tot_h, 1) if tot_h else None
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("act_w")
    ap.add_argument("ear_w")
    ap.add_argument("lap_w")
    ap.add_argument("--lap-p", type=float, default=0.4)
    ap.add_argument("--min-p-texting", type=float, default=0.0)
    ap.add_argument("--mouth-k", type=float, default=1.5)
    ap.add_argument("--sets", default="syndd,3mdad,ebdd,dad")
    ap.add_argument("--detect-every", type=int, default=1)
    a = ap.parse_args()
    min_p = {"texting": a.min_p_texting}
    win = syndd_windows()
    result = {"args": vars(a), "datasets": {}}
    for ds in a.sets.split(","):
        rs, act, ph, lap, classes = preds2(a.tag, ds, "test", a.act_w, a.ear_w, a.lap_w)
        variants = {
            "v2": dict(lap_p=a.lap_p, mouth_k=a.mouth_k, min_p=min_p),
            "v2 lap 0.5 (plan)": dict(lap_p=0.5, mouth_k=a.mouth_k, min_p=min_p),
            "v2 no lap check": dict(lap_p=None, mouth_k=a.mouth_k, min_p=min_p),
            "v2 no lap check, texting gate 0.8 (v1 rule)": dict(lap_p=None, mouth_k=a.mouth_k,
                                                                min_p={"texting": 0.8}),
            "v2 no mouth filter": dict(lap_p=a.lap_p, mouth_k=None, min_p=min_p),
        }
        ours = {n: ours_events(rs, act, ph, lap, classes, v["lap_p"], v["min_p"])
                for n, v in variants.items()}
        # clips: (clip, cls, side, s, e), release events, drink/eat events per variant
        clips = []
        if ds == "syndd":
            cids = sorted({r["clip"] for r in rs})
            meta = {r["clip"]: (r["cls"], r["side"]) for r in rs}
            rel_v, frames_v = syndd_release(win, cids)
            de_v = {mk: {stem: drink_eat_events(fr, mk, a.detect_every)
                         for stem, fr in frames_v.items()}
                    for mk in {v["mouth_k"] for v in variants.values()}}
            for c in cids:
                stem, s, e = win[c]
                clips.append((c, *meta[c], s, e, rel_v[stem],
                              {mk: de_v[mk][stem] for mk in de_v}))
        else:
            rc = load_release_clips(ds)
            mks = {v["mouth_k"] for v in variants.values()}
            for c, (cls, side, s, e, frames, rel) in rc.items():
                clips.append((c, cls, side, s, e, rel,
                              {mk: drink_eat_events(frames, mk, a.detect_every) for mk in mks}))
        res = {"clips": len(clips), "hours": round(sum(e - s for _, _, _, s, e, _, _ in clips)
                                                  / 3600, 3)}
        # release
        cl = [{"clip": c, "cls": cls, "side": side, "dur": e - s,
               "onsets": clip_onsets(rel, s, e, cls, REL_KEY)}
              for c, cls, side, s, e, rel, _ in clips]
        res["release"] = summarise(cl, REL_KEY)
        # v1 (all alerts from the action classifier, v1 rows / predictions)
        try:
            rs1, act1, ph1 = preds_v1("v1", ds, "test", None, None)
            dur = {c: e - s for c, _, _, s, e, _, _ in clips}
            v1 = {x["clip"]: x for x in run_clips(rs1, act1, ph1, dur, use_talk=False)}
            cl = [{"clip": c, "cls": cls, "side": side, "dur": e - s,
                   "onsets": v1[c]["onsets"] if c in v1 else {}}
                  for c, cls, side, s, e, _, _ in clips]
            res["v1"] = summarise(cl, OWN_KEY)
        except Exception as ex:  # noqa: BLE001
            res["v1"] = f"not available: {ex!r}"[:200]
        # v2 variants
        for n, v in variants.items():
            cl = []
            for c, cls, side, s, e, _, de in clips:
                ev = {**ours[n].get(c, {}), **de[v["mouth_k"]]}
                cl.append({"clip": c, "cls": cls, "side": side, "dur": e - s,
                           "onsets": clip_onsets(ev, s, e, cls, OWN_KEY)})
            res[n] = summarise(cl, OWN_KEY)
        # frame level (action classifier) + lap phone prob by class
        act7 = act[:, :7].copy()
        if "smoking" in classes:  # hard-negative class: counts as "other" in frame metrics
            act7[:, CLASSES.index("other")] += act[:, classes.index("smoking")]
        cm = confusion(rs, act7)
        plot_cm(cm, f"{ds} test: frame confusion (row %, count)",
                A / "report_assets" / f"cm_{a.tag}_{ds}.png")
        res["frame_acc"] = round(float(np.trace(cm) / cm.sum()), 3)
        res["per_class_frame_acc"] = {CLASSES[i]: round(float(cm[i, i] / cm[i].sum()), 3)
                                      for i in range(len(CLASSES)) if cm[i].sum()}
        res["lap_phone_prob_by_class"] = {
            c: round(float(np.mean([lap[k] for k, r in enumerate(rs) if r["cls"] == c])), 3)
            for c in CLASSES if any(r["cls"] == c for r in rs)}
        result["datasets"][ds] = res
        for n in ("release", "v1", "v2"):
            s_ = res[n]
            if isinstance(s_, dict):
                print(ds, n.ljust(8), {k: v for k, v in s_.items() if k.endswith("recall")
                                       and k not in ("call_L_recall", "call_R_recall")},
                      "FA/h", s_["fa_normal_hof"][2], flush=True)
    (A / "runs" / f"eval_{a.tag}.json").write_text(json.dumps(result, indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
