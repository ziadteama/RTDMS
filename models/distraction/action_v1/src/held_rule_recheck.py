"""Detached D34 val-only rule re-selection; preserve historical defective-rule outputs."""

import itertools
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "_held_data"
DEST = OUT / "rule_d34"


def log(message):
    line = f"[{time.strftime('%H:%M')}] Codex: {message}"
    with open(OUT / "LIVE.log", "a", encoding="utf8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def save(name, value):
    path = DEST / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf8")


def worker():
    import phase_b as b

    val_ids = {j["clip"] for j in b.windows("val")}
    test_ids = {j["clip"] for j in b.windows("test")}
    summaries = {}
    for campaign, root, settings in (
        ("phaseB_loose", OUT / "phaseB", {"loose": (0.35, 1.25)}),
        ("v2", OUT / "held_object_v2/evaluation", {"v2_n": (0.35, 1.25), "v2_s": (0.35, 1.25)}),
    ):
        log(f"D34 {campaign}: loading saved val predictions; test scores not used in selection")
        scenes = [
            json.loads(p.read_text(encoding="utf8")) for p in (root / "predictions").glob("*.json")
        ]
        val = [s for s in scenes if s["job"]["dataset"] == "syndd" and s["job"]["clip"] in val_ids]
        if {s["job"]["clip"] for s in val} != val_ids:
            raise RuntimeError(f"R1 incomplete {campaign} val predictions")
        candidates = []
        for setting in settings:
            metric_path = root / setting / "crop_val.json"
            crop = json.loads(metric_path.read_text(encoding="utf8"))
            backend = next(iter(crop))
            model = setting + "/" + backend
            for i, (p, x, window) in enumerate(
                itertools.product(
                    (0.5, 0.6, 0.7, 0.8, 0.9, 0.95), (5, 10, 15), (0.3, 0.5, 1.0, 1.5)
                )
            ):
                params = dict(p=p, x=x, window=window)
                score = b.score(val, setting, model, params)
                candidates.append(
                    dict(
                        setting=setting,
                        model=model,
                        path=crop[backend]["model"],
                        auc=crop[backend]["auc"],
                        params=params,
                        val=score,
                    )
                )
                if i % 18 == 0:
                    log(f"D34 {campaign} {model}: val grid {i + 1}/72")
        chosen = max(candidates, key=lambda c: (c["val"]["objective"], c["auc"]))
        save(
            f"{campaign}/selection.json",
            dict(
                chosen=chosen,
                candidates=candidates,
                rule="D34 cadence-aware coverage and sip",
                test_used=False,
            ),
        )
        log(
            f"Read D34 {campaign} locked val selection: {chosen['model']} {chosen['params']}; "
            f"recall={chosen['val']['drinking_recall']} FA={chosen['val']['fa_normal_hof']}"
        )
        setting, model = chosen["setting"], chosen["model"]
        results = {}
        for ds in ("syndd", "3mdad", "dad"):
            tests = [
                s
                for s in scenes
                if s["job"]["dataset"] == ds and (ds != "syndd" or s["job"]["clip"] in test_ids)
            ]
            if not tests:
                raise RuntimeError(f"R1 no {campaign} {ds} cached scenes")
            key = setting + "|" + model
            missing = not any(key in f["probs"] for s in tests for f in s["frames"])
            if missing:
                # A different val-only winner may lack test scores. Generate them in a new
                # root, retaining original predictions and all test actions unchanged.
                b.ROOT = DEST / campaign / "new_inference"
                b.ROOT.mkdir(parents=True, exist_ok=True)
                log(
                    f"D34 {campaign} {ds}: selected model missing test predictions; "
                    "new detached inference, transient crops only, no training"
                )
                tests = [
                    b.predict_job(
                        s["job"],
                        {model: (chosen["path"], "cup_bottle")},
                        {setting: settings[setting]},
                    )
                    for s in tests
                ]
            results[ds] = b.score(tests, setting, model, chosen["params"])
            save(f"{campaign}/test_results.json", results)
            value = json.loads((DEST / campaign / "test_results.json").read_text())[ds]
            log(
                f"Read D34 {campaign} {ds}: drinking={value['drinking_recall']} "
                f"FA={value['fa_normal_hof']}; false classes={value['drinking_false_by_class']}"
            )
        summaries[campaign] = dict(chosen=chosen, tests=results)
    path = BASE / "results.md"
    text = path.read_text(encoding="utf8") if path.exists() else "# Held-object results\n"
    lines = [
        "",
        "## D34 frame-rate correction (2026-11-14)",
        "",
        "The old rule (frame-rate bug) produced 3MDAD 0/30. That result is retained above. "
        "Coverage failed because a 0.3s window retained one sample at 3fps. The correction "
        "was decided from frame spacing, not test scores. Effective window=max(configured, "
        "2.5*median interval); coverage needs >=2 eligible samples or >=80% window span. "
        "Sip needs >=2 consecutive confirmed samples spanning max(dt, .5-.5*dt) seconds. "
        "At 3fps this is 1/3s; at 10/20fps observed sip spans are .5s. No tests tune thresholds.",
        "",
        "The live Pi baseline is OFF (`--no-detect`), 0 drinking alerts. The historical "
        "Phase B loose SynDD result was 10/18 and 9.7 FA/h, worse than release 15/18 and "
        "0 FA/h; those historical numbers are unchanged.",
        "",
        "| Campaign | Dataset | Fixed rule true drinking clips | Missed | FA/h |",
        "|---|---|---|---|---|",
    ]
    for campaign, result in summaries.items():
        for ds, metrics in result["tests"].items():
            hit, total = metrics["drinking_recall"]
            lines.append(
                f"| {campaign} | {ds} | {hit}/{total} | {total - hit} | "
                f"{metrics['fa_normal_hof'][2]} |"
            )
    path.write_text(text + "\n".join(lines) + "\n", encoding="utf8")
    save(
        "complete.json",
        dict(success=True, val_only_selection=True, old_outputs_preserved=True, results=summaries),
    )


def supervisor():
    success, reason = False, "not completed"
    log(f"Starting detached JOB rulefix; PID {os.getpid()}; val grid then test; expected 5-30min")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-B", "-u", str(Path(__file__).resolve()), "--worker"],
            cwd=str(BASE.parents[2]),
        )
        save("job.json", dict(supervisor_pid=os.getpid(), child_pid=proc.pid, state="running"))
        if proc.wait():
            raise RuntimeError(f"rulefix child exited {proc.returncode}; inspect stderr")
        success = True
    except BaseException as exc:
        reason = " ".join(str(exc).split())
        traceback.print_exc()
    finally:
        save(
            "job.json",
            dict(
                supervisor_pid=os.getpid(),
                state="done" if success else "failed",
                reason=None if success else reason,
            ),
        )
        log("JOB rulefix DONE" if success else f"JOB rulefix FAILED: {reason}")


if __name__ == "__main__":
    (worker if "--worker" in sys.argv else supervisor)()
