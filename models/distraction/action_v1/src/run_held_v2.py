"""Detached v2 supervisor; gates training on successful phaseB and v2labels jobs."""

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "_held_data"


def log(message):
    line = f"[{time.strftime('%H:%M')}] Codex: {message}"
    with open(OUT / "LIVE.log", "a", encoding="utf8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def run(stage, job):
    status = dict(job=job, pid=os.getpid(), state="running", started=time.strftime("%F %T"))
    path = OUT / f"{job}_job.json"
    success, reason = False, "not completed"
    try:
        path.write_text(json.dumps(status, indent=2), encoding="utf8")
        if stage == "train":
            while True:
                states = {
                    j: json.loads((OUT / f"{j}_job.json").read_text())["state"]
                    if (OUT / f"{j}_job.json").exists()
                    else "waiting"
                    for j in ("phaseB", "v2labels")
                }
                if "failed" in states.values():
                    raise RuntimeError(f"Prerequisite failed: {states}")
                if all(s == "done" for s in states.values()):
                    live = (OUT / "LIVE.log").read_text(encoding="utf8")
                    if all(f"JOB {j} DONE" in live for j in states):
                        break
                log(f"v2train waiting for successful prerequisites: {states}; no GPU training")
                time.sleep(60)
        log(f"Starting detached JOB {job}; {stage}; PID {os.getpid()}")
        proc = subprocess.Popen(
            [sys.executable, "-B", "-u", str(HERE / "held_v2.py"), stage], cwd=str(HERE.parents[3])
        )
        status["child_pid"] = proc.pid
        path.write_text(json.dumps(status, indent=2), encoding="utf8")
        if proc.wait():
            raise RuntimeError(f"{stage} child exited {proc.returncode}; inspect job stderr")
        expected = "labels_complete.json" if stage == "labels" else "v2_complete.json"
        if not (OUT / "held_object_v2" / expected).is_file():
            raise RuntimeError(f"Missing completion evidence {expected}")
        success = True
    except BaseException as exc:
        reason = " ".join(str(exc).split())
        traceback.print_exc()
    finally:
        status.update(
            state="done" if success else "failed",
            reason=None if success else reason,
            finished=time.strftime("%F %T"),
        )
        path.write_text(json.dumps(status, indent=2), encoding="utf8")
        log(f"JOB {job} DONE" if success else f"JOB {job} FAILED: {reason}")
        if stage == "train":
            log("JOB v2 DONE" if success else f"JOB v2 FAILED: {reason}")


if __name__ == "__main__":
    stage = sys.argv[1]
    if stage not in ("labels", "train"):
        raise SystemExit("labels or train required")
    run(stage, "v2labels" if stage == "labels" else "v2train")
