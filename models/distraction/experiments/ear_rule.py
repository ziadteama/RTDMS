"""Near-ear phones: the hand hides most of the phone, so the detector scores it low (0.1-0.2) and
sometimes as a cup. Rule tried here: a weak phone OR drink box (>= ear_conf) overlapping an ear
zone (a square of side `zone` face widths around face-mesh landmarks 234 / 454) counts as a
phone for the usual 1-s phone rule. Replays the cached SynDD detections (conf >= 0.05) and faces.
python experiments/ear_rule.py val            # sweep on validation
python experiments/ear_rule.py test 0.15 0.8  # score one setting once on test"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from _paths import DATA, REPO

import eval_simple as E
from rtdms_distraction import datasets as D
from rtdms_distraction.config import load_rules_config
from rtdms_distraction.rules import face_scale
from rtdms_distraction.simple_rules import SimpleRules
from rtdms_distraction.types import Box, Detection, FaceObservation

W = Path(f"{DATA}/runs/det_v2d_ir_512/weights/best.pt")
st = W.stat()
KEY = hashlib.sha1(f"{W.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:10]
DETS = Path(f"{DATA}/eval_cache/dets/det_v2d_512_{KEY}/fps10")
FACES = Path(f"{DATA}/eval_cache/faces/fps10")
CONF = {"phone": .40, "drink": .45, "food": .40}
EARS = (234, 454)


def replay(stem, ear_conf, zone, use_drink=True, hold_s=0.0):
    fz = np.load(FACES / f"{stem}.npz")
    dets = np.load(DETS / f"{stem}.npy")
    by_t: dict[float, list] = {}
    for t, k, cf, a, b, c, d in dets:
        by_t.setdefault(round(float(t), 4), []).append((E.NAMES[int(k)], float(cf),
                                                         Box(float(a), float(b), float(c), float(d))))
    r = load_rules_config()
    r.mode = "simple"
    r.simple.texting = False
    rules = SimpleRules(r.simple)
    events = {"phone": [], "drinking": [], "eating": []}
    open_, last_face, t = {}, None, 0.0
    hist = []  # (t, weak ear evidence) for the sustained variant
    for t, ok, lm in zip(fz["t"], fz["ok"], fz["lm"], strict=True):
        face = FaceObservation(lm.astype(np.float64), None, None, None, "none", None,
                               "geometric", 0.0) if ok else None
        if face is not None:
            last_face = (float(t), face)
        raw = by_t.get(round(float(t), 4), [])
        strong = [Detection(n, cf, bx) for n, cf, bx in raw if cf >= CONF[n]]
        held = last_face[1] if last_face and float(t) - last_face[0] <= 1.0 else None
        weak_hit = None
        if ear_conf and held is not None:
            fw = face_scale(held)
            for n, cf, bx in raw:
                if n not in (("phone", "drink") if use_drink else ("phone",)) or cf < ear_conf                         or cf >= CONF[n] and n == "phone":
                    continue
                for e in EARS:
                    x, y = held.landmarks[e]
                    h = zone * fw / 2
                    if bx.x1 < x + h and bx.x2 > x - h and bx.y1 < y + h and bx.y2 > y - h:
                        weak_hit = Detection("phone", cf, bx)
                        break
        if hold_s:
            hist.append((float(t), weak_hit is not None))
            hist = [h for h in hist if float(t) - h[0] <= hold_s]
            sustained = sum(v for _, v in hist) >= 0.7 * len(hist) and                 float(t) - hist[0][0] >= 0.9 * hold_s
            if weak_hit is not None and sustained:
                strong.append(weak_hit)
        elif weak_hit is not None:
            strong.append(weak_hit)
        out = rules.update(float(t), face, strong)
        for b, s in out.items():
            if s["level"] == "alert" and b not in open_:
                open_[b] = float(t)
            elif s["level"] != "alert" and b in open_:
                events[b].append((open_.pop(b), float(t)))
    for b, s in open_.items():
        events[b].append((s, float(t)))
    return events


def run(split_name, ear_conf, zone, use_drink=True, hold_s=0.0):
    split = json.load(open(REPO / "configs" / "syndd_split.json"))
    segs = [s for s in D.syndd(f"{DATA}/public/syndd/A1") if split.get(s.driver) == split_name]
    videos = sorted({str(s.video) for s in segs})
    ev = {v: replay(Path(v).stem, ear_conf, zone, use_drink, hold_s) for v in videos}
    res = E.summarise(E.score(segs, ev))
    row = {k: res[k]["recall"] for k in ("phone_right_ear", "phone_left_ear", "phone_in_hand",
                                         "drinking")}
    row["phone_FA_h"] = round(res["phone_right_ear"]["fa_per_h"], 1)
    row["drink_FA_h"] = round(res["drinking"]["fa_per_h"], 1)
    return row


if __name__ == "__main__":
    sp = sys.argv[1]
    if len(sys.argv) > 2:
        print(sp, sys.argv[2:], run(sp, float(sys.argv[2]), float(sys.argv[3])))
    else:
        print("baseline", run(sp, 0.0, 0.0), flush=True)
        for ec in (0.15, 0.20, 0.25, 0.30):
            for hold in (0.0, 2.0, 3.0):
                print(f"phone-only ear_conf {ec} zone 0.6fw hold {hold}s",
                      run(sp, ec, 0.6, use_drink=False, hold_s=hold), flush=True)
