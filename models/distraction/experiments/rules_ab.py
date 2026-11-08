"""Rules A (texting: head down + wrist low near the lap) and B (eating: repeated hand-to-mouth +
chewing), replayed on the rich cache (10 fps, val / test), combined with the detector-only
simple rules (det_v2d, phone .40 drink .45). Sweep on val, score test once.
python rules_ab.py sweep val | python rules_ab.py test '<json params>'"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import hashlib
import itertools
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np

import eval_simple as E  # noqa: E402
from rtdms_distraction import datasets as D  # noqa: E402
from rtdms_distraction.config import ChewingConfig, load_rules_config  # noqa: E402
from rtdms_distraction.rules import Baseline, ChewingDetector  # noqa: E402

RICH = Path(f"{DATA}/eval_cache/rich/fps10")
W = Path(f"{DATA}/runs/det_v2d_ir_512/weights/best.pt")
st = W.stat()
KEY = hashlib.sha1(f"{W.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:10]
DETS = Path(f"{DATA}/eval_cache/dets/det_v2d_512_{KEY}/fps10")
FACES = Path(f"{DATA}/eval_cache/faces/fps10")
CONF = {"phone": .40, "drink": .45, "food": .40}


def texting_eating(rich, p):
    """-> per-frame levels: texting 0/1/2 (none / warning / alert), eating 0/1."""
    t, ok, pitch, gaze = rich["t"], rich["ok"], rich["pitch"], rich["gaze"]
    lm, kp, jaw, jsrc, lip, gsrc = rich["lm"], rich["kp"], rich["jaw"], rich["jsrc"], rich["lip"], \
        rich["gsrc"]
    base = Baseline(10.0, 30)
    chew = ChewingDetector(ChewingConfig())
    n = len(t)
    tex, eat = np.zeros(n, int), np.zeros(n, int)
    cond_since, last_true = None, -1e9
    events, at_mouth_prev, last_event_t = deque(), False, -1e9
    chew_t = -1e9
    for i in range(n):
        ti = float(t[i])
        face = None
        if ok[i]:
            class F:  # minimal FaceObservation for Baseline
                pass
            face = F()
            face.pitch_deg = None if np.isnan(pitch[i]) else float(pitch[i])
            face.yaw_deg = 0.0
            face.gaze_down = None if np.isnan(gaze[i]) else float(gaze[i])
            face.gaze_source = str(gsrc[i])
            base.update(ti, face)
            if not np.isnan(jaw[i]):
                chew.update(ti, float(jaw[i]), str(jsrc[i]), float(lip[i]))
        k = kp[i]
        # ---------------- rule A: texting
        down = False
        if face is not None and base.ready:
            if face.pitch_deg is not None and face.pitch_deg - base.pitch >= p["pitch"]:
                down = True
            if face.gaze_down is not None and base.gaze is not None and \
                    face.gaze_down - base.gaze >= p["gaze"]:
                down = True
        low = False
        sh = [j for j in (5, 6) if not np.isnan(k[j, 2]) and k[j, 2] >= 0.3]
        wr = [j for j in (9, 10) if not np.isnan(k[j, 2]) and k[j, 2] >= 0.3]
        if len(sh) == 2 and wr:
            sw = float(np.linalg.norm(k[5, :2] - k[6, :2]))
            mid = (k[5, :2] + k[6, :2]) / 2
            low = any(k[j, 1] >= mid[1] + p["low"] * sw and abs(k[j, 0] - mid[0]) <= p["central"] * sw
                      for j in wr)
        elif p["missing_ok"] and len(sh) == 2 and not wr:
            low = True  # hands below the frame (the mirror camera often cannot see the lap)
        cond = down and low
        if cond:
            last_true = ti
            if cond_since is None:
                cond_since = ti
        elif ti - last_true > 0.5:
            cond_since = None
        if cond_since is not None:
            dur = ti - cond_since
            tex[i] = 2 if dur >= p["alert_s"] else 1 if dur >= p["warn_s"] else 0
        # ---------------- rule B: eating
        at_mouth = False
        if ok[i] and wr:
            m = lm[i][[13, 14]].mean(0)
            fw = float(np.linalg.norm(lm[i][234] - lm[i][454])) or 1.0
            at_mouth = any(np.hypot(*(k[j, :2] - m)) <= p["mouth_r"] * fw for j in wr)
        if at_mouth and not at_mouth_prev and ti - last_event_t >= 1.0:
            events.append(ti)
            last_event_t = ti
        at_mouth_prev = at_mouth
        while events and ti - events[0] > 20.0:
            events.popleft()
        if ok[i] and chew.analyze().chewing:
            chew_t = ti
        chewing = ti - chew_t <= 5.0 if p["need_chew"] else True
        eat[i] = 1 if len(events) >= p["min_events"] and chewing else 0
    return t, tex, eat


def intervals(t, on):
    out, s = [], None
    for ti, v in zip(t, on, strict=True):
        if v and s is None:
            s = float(ti)
        elif not v and s is not None:
            out.append((s, float(ti)))
            s = None
    if s is not None:
        out.append((s, float(t[-1])))
    return out


def evaluate(split_name, p, base_only=False):
    split = json.load(open(str(REPO / "configs/syndd_split.json")))
    segs = [s for s in D.syndd(f"{DATA}/public/syndd/A1") if split.get(s.driver) == split_name]
    videos = sorted({str(s.video) for s in segs})
    r = load_rules_config()
    r.mode = "simple"
    res = {"texting_alert": [0, 0], "texting_warn_or_alert": [0, 0], "eating_warn": [0, 0]}
    fa = {k: {} for k in ("texting_warn", "eating_warn", "phone_alert")}
    neg_s = {}
    for v in videos:
        stem = Path(v).stem
        ev = E.replay(FACES / f"{stem}.npz", DETS / f"{stem}.npy", CONF, r)
        rich = np.load(RICH / f"{stem}.npz")
        t, tex, eat = texting_eating(rich, p)
        tex_warn = [] if base_only else intervals(t, tex >= 1)
        tex_alert = [] if base_only else intervals(t, tex >= 2)
        eat_warn = [] if base_only else intervals(t, eat >= 1)
        phone = ev["phone"]
        vs = [s for s in segs if str(s.video) == v]
        for s in vs:
            hit = lambda iv: any(a < s.end_s + 1 and b > s.start_s - 1 for a, b in iv)  # noqa: E731
            if s.label == "phone_in_hand":
                res["texting_alert"][1] += 1
                res["texting_warn_or_alert"][1] += 1
                res["texting_alert"][0] += hit(phone + tex_alert)
                res["texting_warn_or_alert"][0] += hit(phone + tex_warn)
            elif s.label == "eating":
                res["eating_warn"][1] += 1
                res["eating_warn"][0] += hit(ev["eating"] + eat_warn)
            # false alarms: rule fires during a span where that behaviour is absent
            kind = "drinking" if s.label == "drinking" else s.label if s.label in (
                "neg_talking", "neg_singing") else "other_neg" if E.is_negative(s.label) else None
            if kind is None:
                continue
            neg_s[kind] = neg_s.get(kind, 0.0) + (s.end_s - s.start_s)
            for name, iv in (("texting_warn", tex_warn), ("eating_warn", eat_warn),
                             ("phone_alert", phone)):
                n = sum(1 for a, _ in iv if s.start_s <= a < s.end_s)
                fa[name][kind] = fa[name].get(kind, 0) + n
    out = {k: round(h / n, 3) if n else None for k, (h, n) in res.items()}
    tot_h = sum(neg_s.values()) / 3600
    for name in fa:
        out[f"{name}_FA_per_h"] = round(sum(fa[name].values()) / tot_h, 1)
        out[f"{name}_FA_by"] = {k: f"{fa[name].get(k, 0)} in {neg_s[k] / 60:.0f} min"
                                for k in sorted(neg_s)}
    return out


GRID_A = {"pitch": [15, 20, 25], "gaze": [0.3, 0.4, 9.0], "low": [0.6, 1.0], "central": [0.8],
          "missing_ok": [False, True], "warn_s": [2.0, 3.0], "alert_s": [3.0],
          "mouth_r": [1.2], "min_events": [3], "need_chew": [True]}
GRID_B = {"pitch": [99], "gaze": [9.0], "low": [9.0], "central": [0.8], "missing_ok": [False],
          "warn_s": [2.0], "alert_s": [3.0],
          "mouth_r": [0.6, 0.8, 1.2], "min_events": [2, 3, 4], "need_chew": [True, False]}
GRID = GRID_A

if __name__ == "__main__":
    mode, split_name = sys.argv[1], sys.argv[2]
    if mode == "base":
        print(json.dumps(evaluate(split_name, dict((k, v[0]) for k, v in GRID_A.items()),
                                  base_only=True), indent=1))
    elif mode in ("sweepA", "sweepB"):
        GRID = GRID_A if mode == "sweepA" else GRID_B
        keys = list(GRID)
        rows = []
        for vals in itertools.product(*(GRID[k] for k in keys)):
            p = dict(zip(keys, vals, strict=True))
            o = evaluate(split_name, p)
            rows.append((p, o))
            print(json.dumps(p), "->", {k: v for k, v in o.items() if not k.endswith("_by")},
                  flush=True)
        json.dump(rows, open(f"{DATA}/runs/overnight/rules_{mode}_{split_name}.json", "w"),
                  indent=1)
    else:
        p = json.loads(sys.argv[3])
        print(json.dumps(evaluate(split_name, p), indent=1))
