"""IR step 1: frozen driver-disjoint IR split + UNTRIMMED event scoring for every model.

IR sources with drinking/eating labels on disk (dataset_inventory.md): SynDD (monochrome NIR-
sensitive, 69 drivers, time-stamped) and DAD (active IR, 3 drivers, clip-level, drinking only).
Split (frozen in ir_split.json): train = SynDD train drivers (49); val = SynDD-val (10);
test = SynDD-test (10) + DAD Tester1/10/11 (front_IR). Same driver sets as before, so no model
trained so far has seen a val/test driver.

Scoring: SynDD windows = the ANNOTATION (untrimmed; phase_b.windows trims 0.5 s per side), DAD /
3MDAD clip windows unchanged. Drinking: recall over drinking clips, FA/h = false drinking alerts /
hours of ALL non-drinking clips. Eating: same with eating. Models: clean nano (no veto), s control
(no veto), best nano (iteration 6 + phone veto), old box detector (release rules, fixed). Rule
params of our models are re-picked on IR validation (untrimmed SynDD-val) only.

python ir_eval.py [extra predictions dir name=model_key ...]
"""

import importlib
import json
import sys
from collections import Counter

import overnight_fusion as F

IR = F.OUT / "ir"
IR.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(F.HERE.parent.parent / "experiments"), str(F.HERE.parent.parent / "scripts")]


def widen(scenes):
    out = []
    for s in scenes:
        if s["job"]["dataset"] != "syndd":
            out.append(s)
            continue
        iv = [dict(c, s=c["s"] - 0.5, e=c["e"] + 0.5) for c in s["job"]["intervals"]]
        out.append(dict(s, job=dict(s["job"], intervals=iv)))
    return out


def summarise(records, target):
    pos = [r for r in records if r["cls"] == target]
    neg = [r for r in records if r["cls"] != target]
    hours = sum(r["dur"] for r in neg) / 3600
    fa = sum(r["onsets"] for r in neg)
    by = Counter()
    for r in neg:
        by[r["label"]] += r["onsets"]
    return dict(caught=[sum(r["onsets"] > 0 for r in pos), len(pos)], false_alerts=fa,
                hours=round(hours, 3), fa_per_h=round(fa / hours, 2) if hours else None,
                false_by_type={k: v for k, v in sorted(by.items()) if v},
                missed=[r["clip"] for r in pos if not r["onsets"]])


def records_from_metric(m):
    return [dict(clip=c["clip"], cls=c["cls"], label=c["label"], dur=c["dur"], onsets=c["onsets"])
            for c in m["clips"]]


def old_detector(b, split):
    """Release rules (simple mode) events, fixed; SynDD from the cached replay, DAD from
    runs/release_v2. Untrimmed SynDD windows."""
    import evaluate_v2 as e

    recs = {"drinking": [], "eating": []}
    jobs = b.windows(split)
    for job in jobs:
        events = e.ear_rule.replay(job["clip"], 0.0, 0.0) if hasattr(e, "ear_rule") else None
        if events is None:
            import ear_rule

            events = ear_rule.replay(job["clip"], 0.0, 0.0)
        for c in job["intervals"]:
            s, t = c["s"] - 0.5, c["e"] + 0.5
            for target in recs:
                ons = e.clip_onsets(events, s, t, c["cls"], e.REL_KEY).get(target, 0)
                recs[target].append(dict(clip=c["clip"], cls=c["cls"], label=c["label"],
                                         dur=t - s, onsets=ons))
    out = {"syndd": recs}
    if split == "test":
        dad = {"drinking": [], "eating": []}
        for clip, (cls, _side, s, t, _fr, rel) in e.load_release_clips("dad").items():
            for target in dad:
                ons = e.clip_onsets(rel, s, t, cls, e.REL_KEY).get(target, 0)
                dad[target].append(dict(clip=clip, cls=cls, label=clip.split("_", 1)[1],
                                        dur=t - s, onsets=ons))
        out["dad"] = dad
    return out


def main():
    b = importlib.import_module("phase_b")
    b.DrinkingRule = importlib.import_module("held_alerts").DrinkingRule
    measure = importlib.import_module("overnight_measure")
    val_clips = {j["clip"] for j in b.windows("val")}
    test_clips = {j["clip"] for j in b.windows("test")}
    split = dict(
        frozen="2026-11-14", sources="SynDD rear view (monochrome/NIR) + DAD front_IR",
        train=sorted({j["driver"] for j in b.windows("train")}) if hasattr(b, "windows") else None,
        val=sorted({j["driver"] for j in b.windows("val")}),
        test=sorted({j["driver"] for j in b.windows("test")}) + ["dad_Tester1", "dad_Tester10",
                                                                 "dad_Tester11"],
        windows="SynDD untrimmed annotation; DAD clip folders",
        rule="choices on IR val only; IR test report-only")
    assert not set(split["val"]) & set(split["test"])
    if split["train"]:
        assert not set(split["train"]) & (set(split["val"]) | set(split["test"]))
    (IR / "ir_split.json").write_text(json.dumps(split, indent=1))
    rows = {}
    rows.update(F.phone_rows("syndd", "val"))
    for ds in ("syndd", "dad"):
        rows.update(F.phone_rows(ds, "test"))
    clean_sel = json.loads((F.CLEAN / "selection.json").read_text())["selections"]
    models = {
        "clean nano (no veto)": (F.CLEAN, clean_sel["nano"]["model"], "nano", False),
        "s control (no veto)": (F.CLEAN, clean_sel["control"]["model"], "control", False),
        "best nano: iteration 6 + phone veto": (F.OUT / "overnight/distill_rw", "nano/fp32",
                                               "nano", True),
    }
    for extra in sys.argv[1:]:
        name, key = extra.split("=")
        models[name] = (F.OUT / name, key, "nano", True)
    results = {"split": split, "models": {}}
    for name, (root, model, setting, phone) in models.items():
        sc = [json.loads(p.read_text()) for p in (root / "predictions").glob("*.json")]
        val = widen([s for s in sc if s["job"]["dataset"] == "syndd"
                     and s["job"]["clip"] in val_clips])
        test = {"syndd": widen([s for s in sc if s["job"]["dataset"] == "syndd"
                                and s["job"]["clip"] in test_clips]),
                "dad": [s for s in sc if s["job"]["dataset"] == "dad"]}
        val = F.apply(val, rows, phone, None)
        test = {k: F.apply(v, rows, phone, None) for k, v in test.items()}
        # Re-pick rule params on IR validation (untrimmed SynDD-val), val only.
        best = None
        for p, x, w in F.GRID:
            params = dict(p=p, x=x, window=w)
            m = measure.metric(b, val, setting, model, params)
            obj = m["recall"][0] / m["recall"][1] - 0.02 * m["fa_per_h"]
            if best is None or obj > best[0]:
                best = (obj, params, m)
        _, params, vm = best
        res = dict(params=params, phone_veto=phone,
                   val=dict(drinking=summarise(records_from_metric(vm), "drinking")),
                   test={})
        for ds, ss in test.items():
            tm = measure.metric(b, ss, setting, model, params)
            res["test"][ds] = dict(drinking=summarise(records_from_metric(tm), "drinking"),
                                   eating="no eating model")
        results["models"][name] = res
        F.log(f"IR eval {name} {params}: val {res['val']['drinking']['caught']} "
              f"{res['val']['drinking']['fa_per_h']}/h; test SynDD {res['test']['syndd']['drinking']['caught']} "
              f"{res['test']['syndd']['drinking']['fa_per_h']}/h, DAD {res['test']['dad']['drinking']['caught']} "
              f"{res['test']['dad']['drinking']['fa_per_h']}/h")
    od_val, od_test = old_detector(b, "val"), old_detector(b, "test")
    results["models"]["old box detector (release rules, fixed)"] = dict(
        val={t: summarise(r, t) for t, r in od_val["syndd"].items()},
        test={ds: {t: summarise(r, t) for t, r in v.items()} for ds, v in od_test.items()})
    od = results["models"]["old box detector (release rules, fixed)"]
    F.log(f"IR eval old detector: val drink {od['val']['drinking']['caught']} {od['val']['drinking']['fa_per_h']}/h "
          f"eat {od['val']['eating']['caught']}; test SynDD drink {od['test']['syndd']['drinking']['caught']} "
          f"{od['test']['syndd']['drinking']['fa_per_h']}/h eat {od['test']['syndd']['eating']['caught']} "
          f"{od['test']['syndd']['eating']['fa_per_h']}/h; DAD drink {od['test']['dad']['drinking']['caught']} "
          f"{od['test']['dad']['drinking']['fa_per_h']}/h")
    # DAD drinking misses of the best nano: cup detected low vs not at all.
    sc = [json.loads(p.read_text()) for p in (F.OUT / "overnight/distill_rw/predictions").glob("dad_*drinking*.json")]
    diag = []
    for s in sc:
        fr = s["frames"]
        near = [f for f in fr if f["near"]["nano"]]
        ps = [f["probs"].get("nano|nano/fp32") for f in near if f["probs"].get("nano|nano/fp32") is not None]
        diag.append(dict(clip=s["job"]["clip"], frames=len(fr), hand_at_mouth_frames=len(near),
                         max_cup=max(ps, default=None), frames_cup_over_0_5=sum(p > 0.5 for p in ps),
                         frames_cup_over_0_9=sum(p > 0.9 for p in ps)))
    results["dad_drinking_diagnosis"] = diag
    F.log(f"IR eval DAD drinking diagnosis: {diag}")
    (IR / "ir_results.json").write_text(json.dumps(results, indent=1))
    F.log("JOB ir_eval DONE")


if __name__ == "__main__":
    main()
