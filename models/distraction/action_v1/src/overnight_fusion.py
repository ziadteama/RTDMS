"""Overnight S2.1 / S2.2: fusion-stage vetoes on the clean nano drinking predictions (no retraining).

- phone veto: no drinking while the phone pipeline's call/texting alert is on (same AlertLogic and
  thresholds as scripts/hybrid.py), or was on in the last 2 s. The phone models are only RUN, never
  changed (H1).
- yawn veto: no drinking while lip gap / face width (face mesh, from the extraction CSV) > threshold.

Every choice is made on validation (SynDD-val + frozen 3MDAD-val drivers) with the clean-run
objective (mean recall - 0.02 x pooled all-non-drinking FA/h). Test is scored once afterwards,
report only.

python overnight_fusion.py
"""

import bisect
import csv
import importlib
import itertools
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "scripts")]
OUT = HERE.parent / "_held_data"
CLEAN = OUT / "overnight/clean"
ROOT = OUT / "overnight/fusion"
ROOT.mkdir(parents=True, exist_ok=True)
A = Path("D:/rtdms-data/action_v1")
RUNS = A / "runs"
GRID = list(itertools.product((0.5, 0.6, 0.7, 0.8, 0.9, 0.95), (5, 10, 15), (0.3, 0.5, 1.0, 1.5)))


def log(msg):
    import time

    line = f"[{time.strftime('%H:%M')}] Claude: {msg}"
    with open(OUT / "LIVE.log", "a", encoding="utf8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def save(name, obj):
    (ROOT / name).write_text(json.dumps(obj, indent=1, default=str), encoding="utf8")


def phone_rows(ds, split, drivers=None):
    """CSV rows + phone alert state + lip per row. Cached v2 predictions where they exist."""
    import evaluate_v2 as E
    from hybrid_alerts import AlertLogic

    E.PRED = ROOT / "preds"
    act_w = RUNS / "act_n224/weights/best.pt"
    ear_w = RUNS / "phone_n128/weights/best.pt"
    lap_w = RUNS / "phone_lap_n128/weights/best.pt"
    cached = RUNS / "preds" / f"v2_{ds}_{split}_v2.npz"
    rs = E.rows2(ds, split)
    classes = E.act_classes(act_w)
    if drivers is not None:
        keep = [i for i, r in enumerate(rs) if r["driver"] in drivers]
        rs = [rs[i] for i in keep]
        f = ROOT / "preds" / f"ovn_{ds}_{split}_{len(rs)}.npz"
        if f.exists():
            z = np.load(f)
            act, ph, lap = z["act"], z["ph"], z["lap"]
        else:
            f.parent.mkdir(exist_ok=True)
            d = A / "data"
            act = E.predict(act_w, [str(d / r["up"]) for r in rs], classes, 224)
            pr = E.predict(ear_w, [str(d / r["ear_r"]) for r in rs], ["phone_in_hand"], 128)[:, 0]
            pl = E.predict(ear_w, [str(d / r["ear_l"]) for r in rs], ["phone_in_hand"], 128)[:, 0]
            lap = E.predict(lap_w, [str(d / r["lap"]) for r in rs], ["phone_in_hand"], 128)[:, 0]
            ph = np.stack([pr, pl], 1)
            np.savez(f, act=act, ph=ph, lap=lap)
    else:
        z = np.load(cached)
        act, ph, lap = z["act"], z["ph"], z["lap"]
        assert len(act) == len(rs), (cached, len(act), len(rs))
    by_clip = defaultdict(list)
    for i, r in enumerate(rs):
        by_clip[r["clip"]].append(i)
    out = defaultdict(list)  # scene clip -> [(t, phone_on, lip)]
    for clip, idx in by_clip.items():
        idx.sort(key=lambda i: float(rs[i]["t"]))
        logic = AlertLogic(alerts=("call", "texting"), use_talk=False, lap_p=0.4, phone_p=0.5,
                           min_p={"texting": 0.0}, classes=classes)
        for i in idx:
            probs = [float(p) for p in act[i]]
            top = classes[int(np.argmax(probs))]
            ear = float(max(ph[i])) if top == "call" else None
            lp = float(lap[i]) if top == "texting" else None
            state, _ = logic.update(float(rs[i]["t"]), probs, ear, float(rs[i]["lip"] or 0), lp)
            scene = clip if ds != "syndd" else clip.rsplit("_", 1)[0]
            out[scene].append((float(rs[i]["t"]), state["call"] or state["texting"],
                               float(rs[i]["lip"] or 0), rs[i]["face"] == "yes"))
    for v in out.values():
        v.sort()
    return out


def veto_mask(frames, rows, phone, lip_thr, hold=2.0, near_s=0.75):
    """Per prediction frame: True = drinking suppressed."""
    ts = [r[0] for r in rows]
    mask = []
    for f in frames:
        t, v = f["t"], False
        if rows:
            if phone:
                lo = bisect.bisect_left(ts, t - hold)
                hi = bisect.bisect_right(ts, t + 0.5)
                v = any(rows[k][1] for k in range(lo, hi))
            if not v and lip_thr is not None:
                k = bisect.bisect_left(ts, t)
                cand = [j for j in (k - 1, k) if 0 <= j < len(ts) and abs(ts[j] - t) <= near_s]
                v = any(rows[j][3] and rows[j][2] > lip_thr for j in cand)
        mask.append(v)
    return mask


def apply(scenes, rows, phone, lip_thr):
    out = []
    for s in scenes:
        r = rows.get(s["job"]["clip"], [])
        m = veto_mask(s["frames"], r, phone, lip_thr)
        frames = [dict(f, near={**f["near"], "nano": f["near"]["nano"] and not v})
                  for f, v in zip(s["frames"], m, strict=True)]
        out.append(dict(s, frames=frames))
    return out


def choose(b, measure, val, model):
    best = None
    for p, x, w in GRID:
        params = dict(p=p, x=x, window=w)
        ms = {ds: measure.metric(b, ss, "nano", model, params) for ds, ss in val.items()}
        rec = sum(m["recall"][0] / m["recall"][1] for m in ms.values()) / len(ms)
        fa = sum(m["false_alerts"] for m in ms.values())
        hrs = sum(m["negative_hours"] for m in ms.values())
        obj = rec - 0.02 * fa / hrs
        if best is None or obj > best["objective"]:
            best = dict(params=params, objective=obj, metrics=ms, pooled_fa_per_h=fa / hrs)
    return best


def brief(sel):
    return {ds: dict(recall=m["recall"], fa_per_h=round(m["fa_per_h"], 2),
                     false_by_type={k: v["false_alerts"] for k, v in m["false_by_type"].items()
                                    if v["false_alerts"]})
            for ds, m in sel["metrics"].items()}


def keep(before, after):
    """S3.3: recall may drop <= 1 event on every val set, and pooled FA/h must go down, or recall
    must go up with FA unchanged."""
    drop_ok = all(after["metrics"][ds]["recall"][0] >= before["metrics"][ds]["recall"][0] - 1
                  for ds in before["metrics"])
    rb = sum(m["recall"][0] for m in before["metrics"].values())
    ra = sum(m["recall"][0] for m in after["metrics"].values())
    fa_down = after["pooled_fa_per_h"] < before["pooled_fa_per_h"] - 1e-9
    fa_same = abs(after["pooled_fa_per_h"] - before["pooled_fa_per_h"]) < 1e-9
    return drop_ok and (fa_down or (ra > rb and fa_same))


def main():
    os.chdir(HERE)
    b = importlib.import_module("phase_b")
    b.DrinkingRule = importlib.import_module("held_alerts").DrinkingRule
    measure = importlib.import_module("overnight_measure")
    sel = json.loads((CLEAN / "selection.json").read_text())["selections"]["nano"]
    model = sel["model"]
    frozen = set(json.loads((OUT / "overnight/step0/split_freeze.json").read_text())
                 ["mdad_validation_drivers"])
    scenes = {p.stem: json.loads(p.read_text()) for p in (CLEAN / "predictions").glob("*.json")}
    val_clips = {j["clip"] for j in b.windows("val")}
    test_clips = {j["clip"] for j in b.windows("test")}

    def pick(ds, pred):
        return [s for s in scenes.values() if s["job"]["dataset"] == ds and pred(s["job"])]

    val = {"syndd": pick("syndd", lambda j: j["clip"] in val_clips),
           "3mdad": pick("3mdad", lambda j: j["driver"] in frozen)}
    test = {"syndd": pick("syndd", lambda j: j["clip"] in test_clips),
            "3mdad": pick("3mdad", lambda j: j["driver"] not in frozen),
            "dad": pick("dad", lambda j: True)}
    log(f"Fusion: val scenes {[len(v) for v in val.values()]}, test {[len(v) for v in test.values()]}")
    rows = {}
    rows.update(phone_rows("syndd", "val"))
    rows.update(phone_rows("3mdad", "train", frozen))
    log(f"Fusion: phone/lip rows for {len(rows)} val scenes")

    base = choose(b, measure, val, model)
    log(f"Fusion val baseline (re-selected): {base['params']} {brief(base)}")
    results = dict(baseline=dict(params=base["params"], val=brief(base)))

    phone_val = {ds: apply(ss, rows, True, None) for ds, ss in val.items()}
    ph = choose(b, measure, phone_val, model)
    kept_phone = keep(base, ph)
    log(f"Fusion val +phone veto: {ph['params']} {brief(ph)} -> {'KEPT' if kept_phone else 'REVERTED'}")
    results["phone_veto"] = dict(params=ph["params"], val=brief(ph), kept=kept_phone)

    cur, cur_phone = (ph, True) if kept_phone else (base, False)
    yawn_best = None
    for thr in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40):
        yv = {ds: apply(ss, rows, cur_phone, thr) for ds, ss in val.items()}
        y = choose(b, measure, yv, model)
        y["thr"] = thr
        if yawn_best is None or y["objective"] > yawn_best["objective"]:
            yawn_best = y
    kept_yawn = keep(cur, yawn_best)
    log(f"Fusion val +yawn veto thr={yawn_best['thr']}: {yawn_best['params']} {brief(yawn_best)}"
        f" -> {'KEPT' if kept_yawn else 'REVERTED'}")
    results["yawn_veto"] = dict(thr=yawn_best["thr"], params=yawn_best["params"],
                                val=brief(yawn_best), kept=kept_yawn)
    final = yawn_best if kept_yawn else cur
    lip_thr = yawn_best["thr"] if kept_yawn else None
    save("val_results.json", results)

    # Test: scored once, report only. Without vetoes AND with the kept vetoes.
    trows = {}
    for ds in ("syndd", "3mdad", "dad"):
        trows.update(phone_rows(ds, "test"))
    rep = {}
    for name, (params, phone, thr) in {
        "no_veto": (base["params"], False, None),
        "kept_vetoes": (final["params"], cur_phone or kept_phone, lip_thr),
        "phone_veto_only": (ph["params"], True, None),
    }.items():
        rep[name] = {}
        for ds, ss in test.items():
            m = measure.metric(b, apply(ss, trows, phone, thr), "nano", model, params)
            rep[name][ds] = dict(recall=m["recall"], fa_per_h=round(m["fa_per_h"], 2),
                                 false_by_type={k: v["false_alerts"]
                                                for k, v in m["false_by_type"].items()
                                                if v["false_alerts"]})
        log(f"Fusion TEST report-only {name} {params} phone={phone} lip={thr}: "
            + json.dumps({ds: (v['recall'], v['fa_per_h']) for ds, v in rep[name].items()}))
    results["test_report_only"] = rep
    results["final"] = dict(params=final["params"], phone_veto=cur_phone, yawn_thr=lip_thr)
    save("results.json", results)
    log("JOB fusion DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        log(f"JOB fusion FAILED: {type(e).__name__}: {e}")
        raise
