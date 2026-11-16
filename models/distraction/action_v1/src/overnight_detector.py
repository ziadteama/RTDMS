"""Replay fixed release baseline on SynDD-val; no fitting, inference or source writes."""
import json
import sys
import time
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "_held_data"


def log(message):
    with open(OUT / "LIVE.log", "a", encoding="utf8") as f:
        f.write(f"[{time.strftime('%H:%M')}] Codex: {message}\n")


if __name__ == "__main__":
    try:
        import phase_b as b
        sys.path.insert(0, str(BASE.parent / "experiments"))
        sys.path.insert(0, str(BASE.parent / "scripts"))
        import evaluate_v2 as e
        jobs = b.windows("val")
        windows = {c["clip"]: (j["clip"], c["s"], c["e"])
                   for j in jobs for c in j["intervals"]}
        records = []
        for i, job in enumerate(jobs):
            log(f"Release SynDD-val fixed-cache replay: {i+1}/{len(jobs)} videos")
            events, _ = e.syndd_release(windows, [c["clip"] for c in job["intervals"]])
            for c in job["intervals"]:
                onsets = e.clip_onsets(events[job["clip"]], c["s"], c["e"], c["cls"], e.REL_KEY)
                records.append(dict(c, onsets=onsets.get("drinking", 0), dur=c["e"]-c["s"]))
        positive = [r for r in records if r["cls"] == "drinking"]
        negative = [r for r in records if r["cls"] != "drinking"]
        false = sum(r["onsets"] for r in negative)
        hours = sum(r["dur"] for r in negative)/3600
        result = dict(recall=[sum(r["onsets"] > 0 for r in positive), len(positive)],
            false_alerts=false, negative_hours=hours, fa_per_h=false/hours,
            method="Exact evaluate_v2.syndd_release release baseline replay, fixed settings, no tuning",
            false_by_type={label:sum(r["onsets"] for r in negative if r["label"] == label)
                           for label in sorted({r["label"] for r in negative})}, clips=records)
        dest = OUT / "overnight/step0/detector_val.json"
        dest.write_text(json.dumps(result, indent=2), encoding="utf8")
        actual = json.loads(dest.read_text())
        log(f"Read fixed detector SynDD-val: recall={actual['recall']}, all-negative FA/h={actual['fa_per_h']}")
        with open(BASE / "results.md", "a", encoding="utf8") as f:
            f.write("\n## Fixed detector validation replay\n\n"
                    "| Model | Set | Caught/total | All-negative FA/h |\n|---|---|---|---|\n"
                    f"| eval_v2 release fixed-cache replay | SynDD-val | {actual['recall']} | {actual['fa_per_h']} |\n"
                    "\nNo detector tuning. 3MDAD newly held-out TRAIN drivers lack release-box caches; "
                    "that detector val row is blocked pending offline detector inference.\n")
        log("JOB overnight_detector DONE")
    except BaseException as exc:
        traceback.print_exc()
        log("JOB overnight_detector FAILED: " + " ".join(str(exc).split()))
        sys.exit(1)
