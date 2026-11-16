"""Pi 5 held-object evaluation — WRITTEN OFFLINE 2026-11-14, NOT YET RUN ON THE PI.

Runs the same per-frame stack as pi/start_stream.sh (face mesh + drowsiness + v2 phone model,
no box detector) PLUS the held-object drinking check (pose every 3rd frame + cup crop model +
DrinkingRule, phone veto), on recorded Pi IR clips, and reports:

  1. IR-frame results: drinking caught / total, false alarms per hour over ALL non-drinking clips,
     breakdown by clip type (labels.csv from RECORDING_CHECKLIST.md);
  2. speed: per-stage ms and end-to-end FPS with everything running together;
  3. wrist check: a contact sheet of frames with mouth / wrist / hand point / crop drawn.

python pi_held_eval.py --clips ~/rtdms_rec --model <held cup NCNN dir> [--seconds 60 (live camera)]
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
DIST = HERE.parents[1]
sys.path[:0] = [str(DIST / "src"), str(DIST / "scripts"), str(HERE.parent / "src")]

from held_runtime import H, K, HeldDrinking, hand_geometry  # noqa: E402
from hybrid import Hybrid  # noqa: E402
from run import apply_overrides  # noqa: E402

from rtdms_distraction.capture import open_source  # noqa: E402
from rtdms_distraction.config import (  # noqa: E402
    PoseConfig,
    load_pipeline_config,
    load_rules_config,
    resolve_path,
)
from rtdms_distraction.pipeline import DistractionPipeline  # noqa: E402
from rtdms_distraction.pose import PoseEstimator, driver_person  # noqa: E402

DRINK = "drinking"


class NullDetector:
    def detect(self, view):
        return []


def throttled():
    try:
        return subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"unavailable: {e}"


def build(args, size):
    # Same settings as pi/start_stream.sh: --profile pi --no-rectify --roi full --drowsiness
    # --no-texting --hybrid --no-detect --mesh --rotate 180.
    ns = argparse.Namespace(no_rectify=True, roi="full", driver_side=None, detector_backend=None,
                            weights=None, detect_every=None, hands=None, per_frame_log=False,
                            log_dir=None)
    pcfg = load_pipeline_config(None, "pi")
    rcfg = load_rules_config(None)
    apply_overrides(pcfg, ns)
    rcfg.simple.texting = False
    pipe = DistractionPipeline(pcfg, rcfg, size, detector=NullDetector())
    from drowsiness import Drowsiness

    drowsy = Drowsiness(pipe.roi.out_w, pipe.roi.out_h, str(resolve_path(pcfg.facemesh.model_path)),
                        "litert", "default", str(resolve_path("profiles")))
    hybrid = Hybrid(resolve_path("models/action_v2"))
    pose = PoseEstimator(PoseConfig(weights=str(DIST / "models/yolo26n_pose_320_ncnn_model")))
    sel = json.loads((HERE / "held_params.json").read_text())
    held = HeldDrinking(args.model, HERE / "mouth_fit.json", sel["params"])
    return pipe, drowsy, hybrid, pose, held, sel


def run_source(src, args, label, stats, sheet):
    src.start()
    pipe = drowsy = hybrid = pose = held = None
    kp, n, t_first, onsets = None, 0, None, []
    while True:
        gray, t = src.read()
        if gray is None or (args.seconds and t_first is not None and t - t_first > args.seconds):
            break
        if args.rotate:
            gray = cv2.rotate(gray, cv2.ROTATE_180)
        if pipe is None:
            pipe, drowsy, hybrid, pose, held, _ = build(args, gray.shape[::-1])
        t_first = t if t_first is None else t_first
        t0 = time.perf_counter()
        res = pipe.process(gray, t)
        t1 = time.perf_counter()
        lm = res.face.landmarks if res.face is not None else None
        drowsy.feed(t, lm)
        t2 = time.perf_counter()
        view = res.view if res.view.ndim == 2 else cv2.cvtColor(res.view, cv2.COLOR_BGR2GRAY)
        hy = hybrid.feed(t, view, lm)
        t3 = time.perf_counter()
        if n % 3 == 0:
            person = driver_person(pose.detect(cv2.cvtColor(view, cv2.COLOR_GRAY2BGR)),
                                   None if lm is None else (lm[10] + lm[152]) / 2)
            kp = person.kpts if person else None
        t4 = time.perf_counter()
        pitch = res.face.pitch_deg if res.face is not None else None
        out = held.feed(t, view, lm, kp, pitch, veto=bool(hy.get("call") or hy.get("texting")))
        t5 = time.perf_counter()
        if out["onset"]:
            onsets.append(t - t_first)
        for k, a, b in (("face+pipeline", t0, t1), ("drowsiness", t1, t2), ("phone_v2", t2, t3),
                        ("pose", t3, t4), ("held", t4, t5), ("total", t0, t5)):
            stats[k].append((b - a) * 1000)
        if lm is not None and kp is not None and n % 15 == 0 and len(sheet) < 24:
            tile = cv2.cvtColor(view, cv2.COLOR_GRAY2BGR)
            mouth = (lm[13] + lm[14]) / 2
            fh = float(np.linalg.norm(lm[10] - lm[152]))
            for w in (9, 10):
                if kp[w, 2] >= 0.3:
                    cv2.circle(tile, tuple(int(v) for v in kp[w, :2]), 6, (0, 255, 0), -1)
            cv2.circle(tile, tuple(int(v) for v in mouth), 5, (0, 0, 255), -1)
            cv2.circle(tile, tuple(int(v) for v in mouth), int(K * fh), (255, 160, 0), 2)
            d, crop = hand_geometry(kp, mouth, fh, H)
            if crop is not None:
                c, s = crop
                cv2.rectangle(tile, (int(c[0] - s / 2), int(c[1] - s / 2)),
                              (int(c[0] + s / 2), int(c[1] + s / 2)), (255, 255, 255), 2)
            cv2.putText(tile, f"{label} d={d if d is None else round(d, 2)} cup={out['cup']}",
                        (8, 24), 0, 0.6, (255, 255, 255), 2)
            sheet.append(cv2.resize(tile, (480, int(480 * tile.shape[0] / tile.shape[1]))))
        n += 1
    src.stop()
    dur = (t - t_first) if t_first is not None else 0.0
    return dict(label=label, frames=n, seconds=dur, onsets=onsets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", help="folder with recorded clips + labels.csv (file,label)")
    ap.add_argument("--model", required=True, help="held cup NCNN model dir (INT8 or FP32)")
    ap.add_argument("--seconds", type=float, default=0, help="live camera for N s (no --clips)")
    ap.add_argument("--rotate", action="store_true", default=True)
    ap.add_argument("--out", default=str(Path.home() / "rtdms_held_eval"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = dict(throttled_before=throttled(), model=args.model, started=time.ctime())
    stats, sheet, clips = defaultdict(list), [], []
    if args.clips:
        rows = list(csv.DictReader(open(Path(args.clips) / "labels.csv", encoding="utf8")))
        for r in rows:
            src = open_source(1280, 800, 30, video=str(Path(args.clips) / r["file"]), realtime=False)
            clips.append(run_source(src, args, r["label"], stats, sheet))
            print(f"[held] {r['file']} {r['label']}: onsets at {clips[-1]['onsets']}", flush=True)
    else:
        src = open_source(1280, 800, 30)
        clips.append(run_source(src, args, "live", stats, sheet))
    report["throttled_after"] = throttled()
    report["ms"] = {k: dict(mean=round(float(np.mean(v)), 2), p95=round(float(np.percentile(v, 95)), 2))
                    for k, v in stats.items()}
    report["fps"] = round(1000 / report["ms"]["total"]["mean"], 1) if stats["total"] else None
    pos = [c for c in clips if c["label"] == DRINK]
    neg = [c for c in clips if c["label"] not in (DRINK, "live")]
    hours = sum(c["seconds"] for c in neg) / 3600
    report["drinking_caught"] = [sum(bool(c["onsets"]) for c in pos), len(pos)]
    report["false_alarms"] = sum(len(c["onsets"]) for c in neg)
    report["fa_per_h_all_non_drinking"] = report["false_alarms"] / hours if hours else None
    by = defaultdict(lambda: [0, 0.0])
    for c in neg:
        by[c["label"]][0] += len(c["onsets"])
        by[c["label"]][1] += c["seconds"] / 3600
    report["false_by_type"] = {k: dict(false_alarms=v[0], hours=round(v[1], 3)) for k, v in by.items()}
    report["clips"] = clips
    (out / "report.json").write_text(json.dumps(report, indent=1))
    if sheet:
        w = max(s.shape[1] for s in sheet)
        rows_img = [np.hstack(sheet[i:i + 4] + [np.zeros_like(sheet[0])] * (4 - len(sheet[i:i + 4])))
                    for i in range(0, len(sheet), 4)]
        cv2.imwrite(str(out / "wrist_check.jpg"), np.vstack([r[:, : 4 * w] for r in rows_img]))
    print(json.dumps({k: report[k] for k in ("fps", "ms", "drinking_caught",
                                             "fa_per_h_all_non_drinking", "throttled_before",
                                             "throttled_after")}, indent=1))


if __name__ == "__main__":
    main()
