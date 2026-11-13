"""Detached Phase A job supervisor; launch with Start-Process -WindowStyle Hidden.

The child scripts append detailed progress to LIVE.log. This supervisor appends exactly one
terminal JOB marker on success or a caught failure, and persists process/status metadata.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job", choices=("audit", "build"))
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    out = here.parent / "_held_data"
    out.mkdir(parents=True, exist_ok=True)

    def log(message):
        line = f"[{time.strftime('%H:%M')}] Codex: {message}"
        with open(out / "LIVE.log", "a", encoding="utf8") as stream:
            stream.write(line + "\n")
        print(line, flush=True)

    status_path = out / f"{args.job}_job.json"
    status = dict(job=args.job, supervisor_pid=os.getpid(), state="starting",
                  started=time.strftime("%Y-%m-%d %H:%M:%S"))
    success, reason = False, "supervisor did not complete"
    try:
        status_path.write_text(json.dumps(status, indent=2), encoding="utf8")
        command = [sys.executable, "-B", "-u"]
        if args.job == "audit":
            command += [str(here / "held_wrist.py"), "--workers", str(args.workers)]
        else:
            command += [str(here / "build_held.py"), "--k", "1.0", "--side", "2.0"]
        log(f"Starting detached JOB {args.job}; supervisor PID {os.getpid()}; "
            "resume existing caches; no training")
        child = subprocess.Popen(command, cwd=str(here.parents[3]))
        status.update(state="running", child_pid=child.pid, command=command)
        status_path.write_text(json.dumps(status, indent=2), encoding="utf8")
        returncode = child.wait()
        if returncode:
            raise RuntimeError(f"child exited {returncode}; inspect {args.job} stderr/stdout logs")
        if args.job == "audit":
            complete = json.loads((out / "audit_complete.json").read_text(encoding="utf8"))
            if set(complete["datasets"]) != {"syndd", "3mdad", "ebdd", "dad"}:
                raise RuntimeError("audit completion manifest does not contain all four datasets")
            for ds in complete["datasets"]:
                if not (out / "sheets" / f"wrist_{ds}.jpg").is_file():
                    raise RuntimeError(f"missing {ds} wrist sheet")
            if not (out / "syndd_val_ncnn_agreement.json").is_file():
                raise RuntimeError("missing NCNN/PyTorch agreement results")
        success = True
        status.update(state="done", exit_code=0)
    except BaseException as exc:
        reason = " ".join(str(exc).split()) or type(exc).__name__
        status.update(state="failed", reason=reason)
        traceback.print_exc()
    finally:
        status["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            status_path.write_text(json.dumps(status, indent=2), encoding="utf8")
        finally:
            marker = f"JOB {args.job} DONE" if success else f"JOB {args.job} FAILED: {reason}"
            log(marker)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
