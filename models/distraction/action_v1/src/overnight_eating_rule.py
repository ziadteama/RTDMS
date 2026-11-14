"""Overnight S4.2 — EXPERIMENTAL rule-based eating detector (no food labels used).

Eating = repeated hand-to-mouth visits WITHOUT a cup + chewing:
- visit: a run of frames with the hand at the mouth (same gate as drinking: h=.35, K=1.25) where
  the clean nano cup model says NO cup (P(cup) < 0.5), lasting >= min_visit s;
- alert when >= n_visits visits fall inside a 30 s window AND the lip gap / face width (face mesh)
  varies (std > chew_std) over the 3 s after the latest visit (chewing).

Parameters chosen on SynDD-val only (objective = clip recall - 0.02 x FA/h over all non-eating
clips); SynDD-test scored once, report only. DAD has no eating clips. Phone/drinking vetoes off.

python overnight_eating_rule.py
"""

import bisect
import importlib
import itertools
import json
import os
from collections import deque

import numpy as np
import overnight_fusion as F


def events(scene, rows, model, min_visit, n_visits, chew_std):
    ts = [r[0] for r in rows]
    visits, start, last, out, off = deque(), None, None, [], -1e9
    for f in scene["frames"]:
        t = f["t"]
        p = f["probs"].get("nano|" + model)
        at_mouth = f["near"]["nano"] and p is not None and p < 0.5
        if at_mouth:
            start = t if start is None else start
            last = t
            continue
        if start is not None:
            if last - start >= min_visit - 1e-6:
                visits.append(last)
            start = None
        while visits and t - visits[0] > 30:
            visits.popleft()
        if len(visits) >= n_visits and t - visits[-1] <= 3 and t - off > 30:
            lo, hi = bisect.bisect_left(ts, visits[-1]), bisect.bisect_right(ts, visits[-1] + 3)
            lips = [rows[k][2] for k in range(lo, hi) if rows[k][3]]
            if len(lips) >= 3 and float(np.std(lips)) > chew_std:
                out.append(t)
                off = t
                visits.clear()
    return out


def score(scenes, rows, model, params):
    clips = []
    for s in scenes:
        ev = events(s, rows.get(s["job"]["clip"], []), model, **params)
        for c in s["job"]["intervals"]:
            clips.append(dict(cls=c["cls"], label=c["label"], dur=c["e"] - c["s"],
                              onsets=sum(c["s"] <= a <= c["e"] for a in ev)))
    pos = [c for c in clips if c["cls"] == "eating"]
    neg = [c for c in clips if c["cls"] != "eating"]
    hours = sum(c["dur"] for c in neg) / 3600
    fa = sum(c["onsets"] for c in neg)
    hit = sum(c["onsets"] > 0 for c in pos)
    by = {}
    for c in neg:
        if c["onsets"]:
            by[c["label"]] = by.get(c["label"], 0) + c["onsets"]
    return dict(recall=[hit, len(pos)], false_alerts=fa, fa_per_h=fa / hours if hours else None,
                objective=(hit / len(pos) if pos else 0) - 0.02 * (fa / hours if hours else 0),
                false_by_type=by)


def main():
    os.chdir(F.HERE)
    b = importlib.import_module("phase_b")
    model = json.loads((F.CLEAN / "selection.json").read_text())["selections"]["nano"]["model"]
    scenes = {p.stem: json.loads(p.read_text()) for p in (F.CLEAN / "predictions").glob("syndd_*")}
    val_clips = {j["clip"] for j in b.windows("val")}
    test_clips = {j["clip"] for j in b.windows("test")}
    val = [s for s in scenes.values() if s["job"]["clip"] in val_clips]
    test = [s for s in scenes.values() if s["job"]["clip"] in test_clips]
    vrows, trows = F.phone_rows("syndd", "val"), F.phone_rows("syndd", "test")
    best = None
    for mv, nv, cs in itertools.product((0.3, 0.6, 1.0), (1, 2, 3), (0.005, 0.01, 0.02, 0.04)):
        params = dict(min_visit=mv, n_visits=nv, chew_std=cs)
        m = score(val, vrows, model, params)
        if best is None or m["objective"] > best[1]["objective"]:
            best = (params, m)
    params, vm = best
    tm = score(test, trows, model, params)
    res = dict(experimental=True, params=params, syndd_val=vm, syndd_test_report_only=tm,
               dad="no eating clips in DAD", food_labels_used=False)
    (F.ROOT / "eating_rule.json").write_text(json.dumps(res, indent=1))
    F.log(f"EXPERIMENTAL eating rule {params}: SynDD-val {vm['recall']} {vm['fa_per_h']:.1f} FA/h; "
          f"SynDD-test REPORT ONLY {tm['recall']} {tm['fa_per_h']:.1f} FA/h {tm['false_by_type']}")
    F.log("JOB eating_rule DONE")


if __name__ == "__main__":
    main()
