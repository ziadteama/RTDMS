"""Offline deadline guard: evidence-based morning snapshot by09:20, own jobs stop by10:00."""

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "_held_data"
ROOT = OUT / "overnight"


def log(message):
    with open(OUT / "LIVE.log", "a", encoding="utf8") as f:
        f.write(f"[{time.strftime('%H:%M')}] Codex: {message}\n")


def read(path):
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except (OSError, ValueError):
        return {}


def morning():
    baseline = (ROOT / "step0/results_step0.md").read_text(encoding="utf8")
    clean = read(ROOT / "clean/test_results.json")
    status = [(str(p.relative_to(ROOT)), read(p)) for p in ROOT.rglob("job.json")]
    changes = BASE / "overnight_log.md"
    text = [
        "# Morning report — held object",
        "",
        f"Snapshot {datetime.now():%Y-%m-%d %H:%M} Cairo.",
        "No production phone pipeline/weights or security policy changed. Nano128 is product.",
        "",
        "## M1 Baseline and available overnight evidence",
        "",
        baseline,
        "### Clean leakage-free baseline (available only; not a test-selected winner)",
        "",
        "| Dataset | Model | Caught/total | All-negative FA/h |",
        "|---|---|---|---|",
    ]
    for ds, models in clean.items():
        for model, r in models.items():
            text.append(f"| {ds} | {model} | {r['recall']} | {r['fa_per_h']} |")
    best = read(ROOT / "best.json")
    text += [
        "",
        "Accepted winner pointer (only explicit val-kept evidence):",
        "",
        "```json",
        json.dumps(best, indent=2),
        "```",
        "",
        "## M2 Rule",
        "",
        "Kept c77e01c on nano SynDD-val tie (11/15,0 FA/h); "
        "one production path. Coverage/sip cadence tests3/10/20fps passed25 tests.",
        "",
        "## M3 Changes and outcomes",
        "",
        changes.read_text(encoding="utf8") if changes.exists() else "No iteration log available.",
        "",
        "Job states at snapshot:",
        "",
        "```json",
        json.dumps(status, indent=2),
        "```",
        "",
        "## M4 Remaining failure cases",
        "",
        "See per-clip diagnostics under _held_data/overnight/. If example sheets are missing, "
        "they are unverified; no visual review is claimed. All hard clips retained.",
        "",
        "## M5 Eating",
        "",
        "Human labels not read tonight. DAD has no TRAIN drivers in current split and no "
        "eating action folder found in inspected DAD front-IR layout: DAD training queue "
        "addition blocked pending an identified eating source and authorized train-driver split. "
        "CLIP264 flagged originals remain pseudo-labels, not human results. "
        "Experimental repeated-visit/chewing results only count if an evidence file exists.",
        "",
        "## M6 Needs a human / could not verify",
        "",
        "Inspect provisional CLIP groups (k6),816 uncertain crops and top200 OOF suspects. "
        "Human food labelling remains separate. Pi IR wrist, labelled crop quality and "
        "concurrent FPS are BLOCKED: reachable Pi plus recorded/labelled IR clips required. "
        "No Pi/SSH contact tonight. INT8 blocked by Application Control; use an authorized "
        "target-side toolchain, never alter Windows policy. Detector original-action subtype "
        "breakdown is absent from aggregated eval_v2_det2 JSON; do not invent it.",
        "",
        "## M7 Recommendation",
        "",
        "No production switch-on approved. An offline/recorded Pi test is appropriate only "
        "after the nano candidate is explicitly kept on both clean validation sets, target "
        "latency/quality is measured with phone+face running, and failure sheets are reviewed. "
        "DAD2/2 alone is insufficient. Test performance never chooses the candidate.",
    ]
    (BASE / "morning_report.md").write_text("\n".join(text) + "\n", encoding="utf8")
    log("Morning report M1-M7 snapshot written from actual artifacts; pending items labelled")


def stop_own_jobs():
    for p in ROOT.rglob("job.json"):
        status = read(p)
        pid = status.get("pid")
        if status.get("state") != "running" or not pid or pid == os.getpid():
            continue
        # Verify the registered PID is still one of our overnight scripts before killing its tree.
        query = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine",
            ],
            capture_output=True,
            text=True,
        )
        if "overnight_" in query.stdout:
            log(f"10:00 boundary: stopping own overnight process tree{pid}")
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


if __name__ == "__main__":
    log(f"Deadline guard started PID{os.getpid()}; morning snapshot09:20, own work stop09:59:50")
    wrote, heartbeat = False, 0
    while True:
        now = datetime.now()
        if (now.hour, now.minute) >= (9, 20) and not wrote:
            morning()
            wrote = True
        if (now.hour, now.minute, now.second) >= (9, 59, 50):
            stop_own_jobs()
            morning()
            log("OVERNIGHT DONE")
            break
        if time.time() - heartbeat >= 600:
            log("Deadline guard: offline jobs may continue; report due09:20, hard stop10:00")
            heartbeat = time.time()
        time.sleep(5)
