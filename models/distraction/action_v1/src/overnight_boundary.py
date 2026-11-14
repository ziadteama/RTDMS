"""Measurement finding (reported, not used for any keep decision): SynDD event windows in
phase_b.windows() are the annotation TRIMMED by 0.5 s at both ends (a crop-label cleanliness
choice), so a drinking alert in the first half-second of a real sip is scored as a miss. This
re-scores fixed configurations with the untrimmed SynDD annotation (s - 0.5, e + 0.5); 3MDAD and
DAD windows are untrimmed already and are unchanged. Parameters are NOT re-selected.

python overnight_boundary.py
"""

import importlib
import json

import overnight_fusion as F


def widen(scenes):
    out = []
    for s in scenes:
        if s["job"]["dataset"] != "syndd":
            out.append(s)
            continue
        iv = [dict(c, s=c["s"] - 0.5, e=c["e"] + 0.5) for c in s["job"]["intervals"]]
        out.append(dict(s, job=dict(s["job"], intervals=iv)))
    return out


def main():
    b = importlib.import_module("phase_b")
    b.DrinkingRule = importlib.import_module("held_alerts").DrinkingRule
    measure = importlib.import_module("overnight_measure")
    frozen = set(json.loads((F.OUT / "overnight/step0/split_freeze.json").read_text())
                 ["mdad_validation_drivers"])
    val_clips = {j["clip"] for j in b.windows("val")}
    test_clips = {j["clip"] for j in b.windows("test")}
    clean_model = json.loads((F.CLEAN / "selection.json").read_text())["selections"]["nano"]
    configs = {
        "clean nano, no veto": (F.CLEAN, clean_model["model"], clean_model["params"], False),
        "clean nano + phone veto": (F.CLEAN, clean_model["model"],
                                    json.loads((F.ROOT / "results.json").read_text())["final"]["params"],
                                    True),
        "distilled nano + phone veto": (F.OUT / "overnight/distill", "nano/fp32",
                                        dict(p=0.9, x=5, window=0.3), True),
    }
    rows = {}
    rows.update(F.phone_rows("syndd", "val"))
    rows.update(F.phone_rows("3mdad", "train", frozen))
    for ds in ("syndd", "3mdad", "dad"):
        rows.update(F.phone_rows(ds, "test"))
    res = {}
    for name, (root, model, params, phone) in configs.items():
        sc = [json.loads(p.read_text()) for p in (root / "predictions").glob("*.json")]
        sets = {
            "syndd_val": [s for s in sc if s["job"]["dataset"] == "syndd" and s["job"]["clip"] in val_clips],
            "syndd_test": [s for s in sc if s["job"]["dataset"] == "syndd" and s["job"]["clip"] in test_clips],
        }
        res[name] = {}
        for k, ss in sets.items():
            for tag, scenes in (("trimmed", ss), ("untrimmed", widen(ss))):
                m = measure.metric(b, F.apply(scenes, rows, phone, None), "nano", model, params)
                res[name][f"{k}/{tag}"] = dict(recall=m["recall"], fa_per_h=round(m["fa_per_h"], 2))
        F.log(f"Boundary re-score {name}: {res[name]}")
    (F.OUT / "overnight/boundary.json").write_text(json.dumps(res, indent=1))
    F.log("JOB boundary DONE")


if __name__ == "__main__":
    main()
