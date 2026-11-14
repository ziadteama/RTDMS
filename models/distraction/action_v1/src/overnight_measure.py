"""Overnight Step 0: frozen splits, validation-only rule comparison, unified FA metric.

No training, deployment changes, Pi contact, deletion, or original artifact writes.
Historical rule implementations are read from git for measurement, never runtime options.
"""

# ruff: noqa: E402
import csv
import importlib
import itertools
import json
import os
import random
import subprocess
import sys
import time
import traceback
from pathlib import Path
from types import ModuleType

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "_held_data"
ROOT = OUT / "overnight/step0"
ROOT.mkdir(parents=True, exist_ok=True)


def log(message):
    line = f"[{time.strftime('%H:%M')}] Codex: {message}"
    with open(OUT / "LIVE.log", "a", encoding="utf8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def save(name, value):
    dest = ROOT / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(value, indent=2), encoding="utf8")
    return value


def rows(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def metric(b, scenes, setting, model, params):
    result = b.score(scenes, setting, model, params)
    clips = result["clips"]
    negatives = [c for c in clips if c["cls"] != "drinking"]
    false = sum(c["onsets"] for c in negatives)
    hours = sum(c["dur"] for c in negatives) / 3600
    by_label = {
        label: dict(
            false_alerts=sum(c["onsets"] for c in negatives if c["label"] == label),
            hours=sum(c["dur"] for c in negatives if c["label"] == label) / 3600,
        )
        for label in sorted({c["label"] for c in negatives})
    }
    hit, total = result["drinking_recall"]
    return dict(
        recall=[hit, total],
        missed=total - hit,
        false_alerts=false,
        negative_hours=hours,
        fa_per_h=false / hours if hours else None,
        objective=hit / total - 0.02 * false / hours if hours and total else None,
        false_by_type=by_label,
        clips=clips,
    )


def frozen_splits(b):
    report = {}
    for ds in ("syndd", "3mdad", "ebdd", "dad"):
        rr = rows(b.W.DATA / f"action_v1/data/v2/{ds}.csv")
        split = {
            s: sorted({r["driver"] for r in rr if r["split"] == s})
            for s in ("train", "val", "test")
        }
        for a, c in (("train", "val"), ("train", "test"), ("val", "test")):
            if set(split[a]) & set(split[c]):
                raise RuntimeError(
                    f"R1 split overlap {ds} {a}/{c}: {set(split[a]) & set(split[c])}"
                )
        report[ds] = split
    source = rows(OUT / "crops_loose_h035_k125/manifest.csv")
    for r in source:
        if r["driver"] not in report[r["dataset"]][r["split"]]:
            raise RuntimeError(f"Unexpected crop driver/split: {r['path']}")
    drivers = sorted(report["3mdad"]["train"], key=lambda d: int(d.split("_s")[1]))
    heldout = sorted(random.Random(28).sample(drivers, 5))
    freeze = save(
        "split_freeze.json",
        dict(
            seed=28,
            original=report,
            mdad_validation_drivers=heldout,
            mdad_training_drivers=[d for d in drivers if d not in heldout],
            test_drivers_unchanged=True,
            source_manifest_sha256=__import__("hashlib")
            .sha256((OUT / "crops_loose_h035_k125/manifest.csv").read_bytes())
            .hexdigest(),
            historical_models_contaminated_for_new_mdad_val=True,
            policy="All subsequent training including control excludes these 5 drivers. Historical models not used for MDAD-val keep decisions.",
        ),
    )
    log(
        f"Read split freeze: no train/val/test overlap in all four sets; 3MDAD heldout={heldout}, remaining train={len(drivers) - 5}"
    )
    dad_jobs = b.other_jobs("dad")
    cached_drinks = [j for j in dad_jobs if j["intervals"][0]["cls"] == "drinking"]
    raw_root = b.W.DATA / "raw/dad/x/DAD"
    available = sorted(
        str(p)
        for tester in raw_root.iterdir()
        if tester.is_dir()
        for p in tester.glob("drinking/front_IR")
        if p.is_dir()
    )
    cached = {str(Path(j["src"])) for j in cached_drinks}
    missing = [p for p in available if p not in cached]
    save(
        "dad_test_freeze.json",
        dict(
            available_drinking_dirs=available,
            cached_drinking_jobs=cached_drinks,
            missing_from_test=missing,
            dad_train_drivers=report["dad"]["train"],
            frozen=not missing,
            note="No DAD train drivers; never use DAD to choose a change.",
        ),
    )
    if missing:
        log(
            f"STEP 0 PARTIAL: DAD additional raw drinking paths need inference before freezing: {missing}"
        )
    else:
        log(
            f"Read DAD test freeze: {len(available)} available drinking clips, all {len(cached_drinks)} already test; no additions"
        )
    return freeze


def worker():
    b = importlib.import_module("phase_b")
    if json.loads((OUT / "rule_d34/job.json").read_text())["state"] != "done":
        raise RuntimeError("Wait for rulefix DONE first")
    frozen_splits(b)
    val_jobs, test_jobs = b.windows("val"), b.windows("test")
    scene_roots = [
        OUT / "held_object_v2/evaluation/predictions",
        OUT / "rule_d34/v2/new_inference/predictions",
    ]
    # Merge model probabilities for identical geometry/timestamps; do not overwrite sources.
    merged = {}
    for root in scene_roots:
        for p in root.glob("*.json"):
            scene = json.loads(p.read_text(encoding="utf8"))
            key = (scene["job"]["dataset"], scene["job"]["clip"])
            if key not in merged:
                merged[key] = scene
            else:
                records = {round(f["t"], 5): f for f in merged[key]["frames"]}
                for f in scene["frames"]:
                    old = records.get(round(f["t"], 5))
                    if old is not None:
                        old["near"].update(f["near"])
                        old["probs"].update(f["probs"])
    val = [merged[("syndd", j["clip"])] for j in val_jobs]
    rules = {}
    gitpath = "models/distraction/action_v1/src/held_alerts.py"
    for commit in ("ea3d6ad", "c77e01c"):
        source = subprocess.check_output(
            ["git", "show", f"{commit}:{gitpath}"], cwd=str(BASE.parents[2]), text=True
        )
        module = ModuleType(f"measurement_only_{commit}")
        exec(compile(source, f"git:{commit}:{gitpath}", "exec"), module.__dict__)
        rules[commit] = module.DrinkingRule
    all_results = {}
    # Product (nano) chooses the single rule; the s control cannot choose runtime policy.
    for commit, rule in rules.items():
        b.DrinkingRule = rule
        all_results[commit] = {}
        for setting in ("v2_n", "v2_s"):
            model = setting + "/fp32"
            candidates = []
            for i, (p, x, window) in enumerate(
                itertools.product(
                    (0.5, 0.6, 0.7, 0.8, 0.9, 0.95), (5, 10, 15), (0.3, 0.5, 1.0, 1.5)
                )
            ):
                params = dict(p=p, x=x, window=window)
                candidates.append(dict(params=params, val=metric(b, val, setting, model, params)))
                if i % 18 == 0:
                    log(f"Step0 validation {commit} {setting}: {i + 1}/72")
            best = max(candidates, key=lambda c: c["val"]["objective"])
            all_results[commit][setting] = best
            log(
                f"Read Step0 val {commit} {setting}: recall={best['val']['recall']}, "
                f"all-negative FA/h={best['val']['fa_per_h']}, params={best['params']}"
            )
    # Tie keeps the currently active cadence-quantised rule, avoiding an unsupported change.
    kept = max(rules, key=lambda c: (all_results[c]["v2_n"]["val"]["objective"], c == "c77e01c"))
    decision = dict(
        kept_rule_commit=kept,
        reason="nano SynDD-val D12 objective; tie keeps current rule",
        test_used=False,
        mdad_val_not_used="historical models trained on new heldout drivers",
        validation=all_results,
    )
    save("rule_selection.json", decision)  # Locked before any test scoring.
    log(f"Read rule_selection.json: kept={kept}, decided only on nano SynDD-val")
    b.DrinkingRule = rules[kept]
    tests = {
        "syndd": [merged[("syndd", j["clip"])] for j in test_jobs],
        "3mdad": [v for (ds, _), v in merged.items() if ds == "3mdad"],
        "dad": [v for (ds, _), v in merged.items() if ds == "dad"],
    }
    test_results = {}
    for setting in ("v2_n", "v2_s"):
        model = setting + "/fp32"
        best = all_results[kept][setting]
        test_results[setting] = {}
        for ds, scenes in tests.items():
            if not scenes or not any(
                setting + "|" + model in f["probs"] for s in scenes for f in s["frames"]
            ):
                test_results[setting][ds] = dict(blocked="missing cached model predictions")
                continue
            result = metric(b, scenes, setting, model, best["params"])
            test_results[setting][ds] = result
            log(
                f"Read Step0 {setting} {ds} test REPORT ONLY: recall={result['recall']} "
                f"all-negative FA/h={result['fa_per_h']}; breakdown={result['false_by_type']}"
            )
    save("test_baseline.json", test_results)
    detector = json.loads((b.W.DATA / "action_v1/runs/eval_v2_det2.json").read_text())
    old = {}
    for ds, scenes in tests.items():
        clips = [c for s in scenes for c in s["job"]["intervals"]]
        hours = sum(c["e"] - c["s"] for c in clips if c["cls"] != "drinking") / 3600
        ref = detector["datasets"][ds]["release"]
        false = {
            key: value
            for key, value in ref["false_alerts"].items()
            if key.startswith("drinking -> ")
        }
        old[ds] = dict(
            recall=ref["drinking_recall"],
            false_alerts=sum(false.values()),
            negative_hours=hours,
            fa_per_h=sum(false.values()) / hours,
            false_by_type=false,
            caveat="Detector false-alert labels aggregated by true class; source JSON lacks original action subtype.",
        )
    save("detector_baseline.json", old)
    lines = [
        "# Overnight measurement baseline",
        "",
        "2026-11-14. Product: yolo26n-cls 128; yolo26s-cls is control only.",
        "FA/h everywhere below = false drinking onsets / ALL non-drinking hours. "
        "Historical normal-only FA/h in earlier documents is a different metric, not comparable.",
        "",
        f"Validation-only rule choice: `{kept}`. No test used to choose.",
        "",
        "## Validation",
        "",
        "| Model | Set | Caught/total | All-negative FA/h |",
        "|---|---|---|---|",
    ]
    for setting in ("v2_n", "v2_s"):
        r = all_results[kept][setting]["val"]
        lines.append(f"| {setting} | SynDD-val | {r['recall']} | {r['fa_per_h']} |")
    lines += [
        "| all historical models | new 3MDAD-val | NOT ELIGIBLE: trained on these drivers | pending clean retrain |",
        "",
        "## Test (report only)",
        "",
        "| Model | Set | Caught/total | All-negative FA/h |",
        "|---|---|---|---|",
    ]
    for model, values in list(test_results.items()) + [("old detector", old)]:
        for ds, r in values.items():
            lines.append(
                f"| {model} | {ds} | {r.get('recall', 'BLOCKED')} | {r.get('fa_per_h', r.get('blocked'))} |"
            )
    lines += [
        "| live Pi --no-detect | all | 0 alerts (OFF) | 0 |",
        "",
        "Frozen 3MDAD holdout and complete split verification: `_held_data/overnight/step0/split_freeze.json`.",
        "Historical bug: old rule 3MDAD 0/30. Historical Phase B loose10/18,9.7 normal-only FA/h was worse than release15/18,0; retained as historical evidence, not the unified metric.",
        "No Pi contact. No label_food results consumed. Detector subtype breakdown cannot be reconstructed from aggregated JSON alone.",
    ]
    (ROOT / "results_step0.md").write_text("\n".join(lines) + "\n", encoding="utf8")
    save(
        "complete.json",
        dict(
            done=True,
            kept_rule_commit=kept,
            historical_rules_measurement_only=True,
            mdad_clean_retrain_needed=True,
            next="apply kept rule, commit iteration, train clean nano/control excluding frozen5",
        ),
    )


def supervise():
    success, reason = False, "not completed"
    log(
        f"Starting detached overnight Step0 measurement, PID{os.getpid()}; expected5-20min; no GPU training"
    )
    try:
        p = subprocess.Popen(
            [sys.executable, "-B", "-u", str(Path(__file__).resolve()), "--worker"],
            cwd=str(BASE.parents[2]),
        )
        save("job.json", dict(pid=os.getpid(), child_pid=p.pid, state="running"))
        if p.wait():
            raise RuntimeError(f"step0 child exited{p.returncode}; inspect stderr")
        success = True
    except BaseException as exc:
        reason = " ".join(str(exc).split())
        traceback.print_exc()
    finally:
        save(
            "job.json", dict(pid=os.getpid(), state="done" if success else "failed", reason=reason)
        )
        log(
            "STEP 0 PARTIAL: measurement ready; apply val-selected rule and clean holdout retrain next"
            if success
            else "STEP 0 PARTIAL: " + reason
        )
        log("JOB overnight0 DONE" if success else "JOB overnight0 FAILED: " + reason)


if __name__ == "__main__":
    (worker if "--worker" in sys.argv else supervise)()
