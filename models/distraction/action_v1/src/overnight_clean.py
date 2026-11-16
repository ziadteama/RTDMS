"""Iteration 1 clean nano/control retrain, frozen driver validation, unified metrics.

No SSH/Pi or food-label reads. No deletions. Original sources are read only.
"""

# ruff: noqa: E402
import importlib
import itertools
import json
import os
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "_held_data"
ROOT = OUT / "overnight/clean"
ROOT.mkdir(parents=True, exist_ok=True)


def log(message):
    line = f"[{time.strftime('%H:%M')}] Codex: {message}"
    with open(OUT / "LIVE.log", "a", encoding="utf8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def save(name, value):
    p = ROOT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2), encoding="utf8")


def deadline():
    if datetime.now().hour >= 10:
        raise TimeoutError("10:00 Cairo stop boundary")


def mdad_jobs(b, drivers):
    jobs = []
    for driver in drivers:
        subject = "S" + driver.split("_s")[1]
        for action, cls in b.W.extract.MDAD_MAP.items():
            src = b.W.DATA / f"raw/3mdad/front/Day-RGB2/RGB2/{subject}/AC{action}"
            count = len(list(src.glob("*.jpg")))
            if not count:
                raise FileNotFoundError(f"R1 missing raw MDAD-val action: {src}")
            clip = f"{subject}_AC{action}"
            jobs.append(
                dict(
                    dataset="3mdad",
                    driver=driver,
                    src=str(src),
                    clip=clip,
                    intervals=[
                        dict(clip=clip, cls=cls, label=f"AC{action}", s=0.0, e=(count - 1) / 3)
                    ],
                )
            )
    return jobs


def cache_loader(b, original, drivers):
    """Supply real mesh geometry for held-out TRAIN drivers missing release JSONs."""

    def load(job):
        if job["dataset"] != "3mdad" or job["driver"] not in drivers:
            return original(job)
        dest = ROOT / "val_face_cache" / f"{job['clip']}.npz"
        if not dest.exists():
            deadline()
            local = OUT / "pose_face" / f"3mdad_{job['clip']}.npz"
            existing = {}
            if local.exists():
                with b.np.load(local) as z:
                    existing = {
                        round(float(t), 3): lm.copy()
                        for t, lm in zip(z["t"], z["lm7"], strict=True)
                    }
            times, meshes, valid = [], [], []
            log(f"Clean MDAD-val mesh cache {job['clip']} starting; existing lm7 reused")
            for i, (t, gray, _) in enumerate(b.W.frames(job)):
                seven = existing.get(round(t, 3))
                if seven is not None:
                    ok = bool(b.np.isfinite(seven).all())
                    lm = b.np.zeros((478, 2), b.np.float32)
                    if ok:
                        lm[[1, 10, 13, 14, 152, 234, 454]] = seven
                else:
                    found = b.W.extract.faces()(gray)
                    ok = found is not None
                    lm = found if ok else b.np.zeros((478, 2), b.np.float32)
                times.append(t)
                meshes.append(lm)
                valid.append(ok)
                if i % 200 == 0:
                    log(f"Clean MDAD-val mesh {job['clip']}: {i} frames")
            dest.parent.mkdir(parents=True, exist_ok=True)
            b.np.savez_compressed(dest, t=times, lm=meshes, ok=valid)
        with b.np.load(dest) as z:
            result = {
                round(float(t), 3): (bool(ok), lm.copy(), None)
                for t, ok, lm in zip(z["t"], z["ok"], z["lm"], strict=True)
            }
        return "overnight_val_mesh", result

    return load


def worker():
    v = importlib.import_module("held_v2")
    b = v.B
    measure = importlib.import_module("overnight_measure")
    freeze = json.loads((OUT / "overnight/step0/split_freeze.json").read_text())
    rule = json.loads((OUT / "overnight/step0/rule_selection.json").read_text())
    if rule["kept_rule_commit"] != "c77e01c":
        raise RuntimeError("Apply validation-kept rule before training")
    b.DrinkingRule = importlib.reload(importlib.import_module("held_alerts")).DrinkingRule
    heldout = set(freeze["mdad_validation_drivers"])
    original = v.read_csv(v.SOURCE)
    binary = [r for r in original if r["target"] in b.CLASSES]
    train = [r for r in binary if r["split"] == "train" and r["driver"] not in heldout]
    val = [r for r in binary if r["split"] == "val" or r["driver"] in heldout]
    assert not {r["driver"] for r in train} & {r["driver"] for r in val}
    v.ROOT = ROOT
    b.ROOT = ROOT
    os.chdir(ROOT)
    save(
        "data.json",
        dict(
            train=len(train),
            val=len(val),
            heldout=sorted(heldout),
            counts=dict(Counter(f"{r['dataset']}/{r['target']}" for r in train)),
            dropping="Only frozen5 drivers moved to validation; no hard samples discarded",
            source_manifest=str(v.SOURCE),
            food_excluded=True,
            class_balance="weighted sampling",
        ),
    )
    log(f"Read clean data.json: train={len(train)}, crop val={len(val)}, heldout={sorted(heldout)}")
    folder = v.link_data("clean_binary", train, val)
    models = {}
    for setting, base in (
        ("nano", Path("C:/Users/youss/projects/RTDMS/models/distraction/models/yolo26n-cls.pt")),
        ("control", Path("D:/rtdms-data/action_v1/src/yolo26s-cls.pt")),
    ):
        deadline()
        weight = v.fit(setting, folder, base, 40)
        path, metric = b.export(setting, weight, folder, val)
        backend = next(iter(metric))
        models[setting + "/" + backend] = (str(path), "cup_bottle")
        save("models.json", models)
    original_loader = b.W.load_cache
    b.W.load_cache = cache_loader(b, original_loader, heldout)
    settings = {"nano": (0.35, 1.25), "control": (0.35, 1.25)}
    # All 15 mapped actions for every validation driver, including phone/reaching/smoking.
    valjobs = {"syndd": b.windows("val"), "3mdad": mdad_jobs(b, sorted(heldout))}
    scenes = {}
    for ds, jobs in valjobs.items():
        scenes[ds] = []
        for i, job in enumerate(jobs):
            deadline()
            scenes[ds].append(b.predict_job(job, models, settings))
            log(f"Clean validation {ds}: {i + 1}/{len(jobs)} clips/scenes")
    selections = {}
    for setting in settings:
        model = next(name for name in models if name.startswith(setting + "/"))
        candidates = []
        for i, (p, x, window) in enumerate(
            itertools.product((0.5, 0.6, 0.7, 0.8, 0.9, 0.95), (5, 10, 15), (0.3, 0.5, 1.0, 1.5))
        ):
            params = dict(p=p, x=x, window=window)
            metrics = {
                ds: measure.metric(b, ss, setting, model, params) for ds, ss in scenes.items()
            }
            recall = sum(m["recall"][0] / m["recall"][1] for m in metrics.values()) / len(metrics)
            fa = sum(m["false_alerts"] for m in metrics.values())
            hours = sum(m["negative_hours"] for m in metrics.values())
            candidates.append(
                dict(
                    params=params,
                    metrics=metrics,
                    objective=recall - 0.02 * fa / hours,
                    model=model,
                    setting=setting,
                )
            )
            if i % 18 == 0:
                log(f"Clean {setting} val-only grid {i + 1}/72")
        selections[setting] = max(candidates, key=lambda c: c["objective"])
        log(
            f"Read clean {setting} validation selection: params={selections[setting]['params']}; "
            f"metrics={ {ds: (m['recall'], m['fa_per_h']) for ds, m in selections[setting]['metrics'].items()} }"
        )
    save(
        "selection.json",
        dict(
            selections=selections,
            tests_used=False,
            policy="nano product, s control; equal-dataset val recall minus .02 pooled negative FA/h",
        ),
    )
    # Baseline retained for leakage-free protocol, not selected using test performance.
    save(
        "kept_before_test.json",
        dict(
            kept=True,
            reason="required clean validation baseline",
            product="nano",
            control="control",
        ),
    )
    tests = {}
    for ds in ("syndd", "3mdad", "dad"):
        jobs = b.windows("test") if ds == "syndd" else b.other_jobs(ds)
        prediction = []
        for i, job in enumerate(jobs):
            deadline()
            prediction.append(b.predict_job(job, models, settings))
            if i % 10 == 0:
                log(f"Clean report-only {ds} test: {i + 1}/{len(jobs)} scenes")
        tests[ds] = {
            setting: measure.metric(b, prediction, setting, choice["model"], choice["params"])
            for setting, choice in selections.items()
        }
        save("test_results.json", tests)
        for setting, m in tests[ds].items():
            log(
                f"Read clean {setting} {ds} test REPORT ONLY: {m['recall']}, all-negative FA/h={m['fa_per_h']}"
            )
    # Event/score diagnosis: preserve every missed positive clip and its gate/cup evidence.
    diagnosis = []
    for ds, ss in scenes.items():
        choice = selections["nano"]
        missed = {
            c["clip"]
            for c in choice["metrics"][ds]["clips"]
            if c["cls"] == "drinking" and not c["onsets"]
        }
        for scene in ss:
            for clip in scene["job"]["intervals"]:
                if clip["clip"] not in missed:
                    continue
                fr = [f for f in scene["frames"] if clip["s"] <= f["t"] <= clip["e"]]
                probs = [f["probs"].get("nano|" + choice["model"], 0) for f in fr]
                near = sum(f["near"]["nano"] for f in fr)
                high = sum(p > choice["params"]["p"] for p in probs)
                cause = (
                    "geometry_gate"
                    if not near
                    else "cup_score"
                    if not high
                    else "rule_timing_or_pitch"
                )
                diagnosis.append(
                    dict(
                        dataset=ds,
                        clip=clip,
                        near_frames=near,
                        high_cup_frames=high,
                        frames=len(fr),
                        max_cup=max(probs, default=0),
                        cause=cause,
                    )
                )
    save("validation_misses.json", diagnosis)
    save(
        "complete.json",
        dict(
            done=True,
            clean_holdout=True,
            product="nano",
            no_pi_contact=True,
            no_food_labels_read=True,
            next="Step1 diagnosis then Step2 fusion/yawn/hard-negative loop",
        ),
    )


def supervise():
    success, reason = False, "not completed"
    log(
        f"Starting detached JOB overnight_clean; supervisor{os.getpid()}; train nano/control, val then test; expected30-75min"
    )
    try:
        p = subprocess.Popen(
            [sys.executable, "-B", "-u", str(Path(__file__).resolve()), "--worker"],
            cwd=str(BASE.parents[2]),
        )
        save("job.json", dict(pid=os.getpid(), child_pid=p.pid, state="running"))
        # Explicit deadline, including an otherwise blocked child process.
        limit = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        try:
            code = p.wait(timeout=max(1, (limit - datetime.now()).total_seconds()))
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            raise TimeoutError("10:00 Cairo stop boundary; own child tree stopped") from None
        if code:
            raise RuntimeError(f"clean child exited{code}; inspect stderr")
        success = True
    except BaseException as exc:
        reason = " ".join(str(exc).split())
        traceback.print_exc()
    finally:
        save(
            "job.json", dict(pid=os.getpid(), state="done" if success else "failed", reason=reason)
        )
        log("STEP 0 DONE" if success else "STEP 0 PARTIAL: " + reason)
        log("JOB overnight_clean DONE" if success else "JOB overnight_clean FAILED: " + reason)


if __name__ == "__main__":
    (worker if "--worker" in sys.argv else supervise)()
