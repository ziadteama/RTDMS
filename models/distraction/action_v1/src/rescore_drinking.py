"""D31: re-score saved drinking predictions with the fixed DrinkingRule (no new inference).

Selection is redone on SynDD-val only, with the same grid and D12 objective as phase_b.evaluation;
test sets are scored once with the locked parameters.

python rescore_drinking.py <root with predictions/>   e.g. _held_data/phaseB
"""

import itertools
import json
import sys
from pathlib import Path

import phase_b as B

root = Path(sys.argv[1])
scenes = {p.stem: json.loads(p.read_text()) for p in (root / "predictions").glob("*.json")}
val_clips = {j["clip"] for j in B.windows("val")}
test_clips = {j["clip"] for j in B.windows("test")}


def pick(ds, clips=None):
    return [s for s in scenes.values()
            if s["job"]["dataset"] == ds and (clips is None or s["job"]["clip"] in clips)]


val = pick("syndd", val_clips)
tests = {"syndd": pick("syndd", test_clips), "3mdad": pick("3mdad"), "dad": pick("dad")}
names = sorted({k for s in val for f in s["frames"] for k in f["probs"]})
out = {"rule": "D31 fixed window", "val_clips": len(val), "models": {}}
for key in names:
    setting, model = key.split("|", 1)
    if model.startswith("old/"):
        continue
    best = None
    for p, x, window in itertools.product((0.5, 0.6, 0.7, 0.8, 0.9, 0.95), (5, 10, 15),
                                          (0.3, 0.5, 1.0, 1.5)):
        params = dict(p=p, x=x, window=window)
        m = B.score(val, setting, model, params)
        if best is None or m["objective"] > best[1]["objective"]:
            best = (params, m)
    params, m = best
    res = {"params": params, "val": dict(recall=m["drinking_recall"], fa=m["fa_normal_hof"])}
    for ds, sc in tests.items():
        if not sc or not any(key in f["probs"] for s in sc for f in s["frames"]):
            res[ds] = "no predictions for this model"
            continue
        t = B.score(sc, setting, model, params)
        res[ds] = dict(recall=t["drinking_recall"], fa_normal_hof=t["fa_normal_hof"],
                       all_negative_fa_per_h=t["negative_false_per_h"],
                       false_by_class={k: v for k, v in t["drinking_false_by_class"].items() if v})
    out["models"][key] = res
    print(key, json.dumps(res))
(root / "rescore_fixed_rule.json").write_text(json.dumps(out, indent=1))
