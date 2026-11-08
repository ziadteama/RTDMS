"""Current release model (det_v2d NCNN, simple rules, phone .40 drink .45 food .40) on the EBDD
test drivers (akkas, jewel), every 3rd frame of 30 fps (10 fps) - for the side-by-side in step 7.
Same pipeline set-up as experiments/mdad3_eval.py. Output: runs/release_ebdd/<video>.json"""
import copy
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2

EXP = Path(r"C:\Users\youss\projects\RTDMS\models\distraction\experiments")
sys.path.insert(0, str(EXP))
import _paths  # noqa: E402,F401  (adds the package src + scripts to sys.path)

OUT = Path("D:/rtdms-data/action_v1/runs/release_ebdd")
ROOT = Path("D:/rtdms-data/raw/ebdd/x")
STEP = 3


def run(video):
    import os
    os.chdir(_paths.REPO)
    from live import build_detector
    from rtdms_distraction.config import LiveModel, load_pipeline_config, load_rules_config
    from rtdms_distraction.pipeline import DistractionPipeline

    v = Path(video)
    out = OUT / f"{re.sub(r'[^A-Za-z_]', '', v.stem).upper()}.json"
    if out.exists():
        return str(out)
    pcfg, rcfg = load_pipeline_config(profile="laptop_webcam"), load_rules_config()
    rcfg.mode = "simple"
    rcfg.simple.texting = False
    pcfg.detector.conf = {"phone": .40, "drink": .45, "food": .40}
    m = LiveModel(name="det_v2d", weights="models/det_v2d_ir_512_ncnn_model", imgsz=512,
                  hands="mediapipe")
    det = build_detector(pcfg.detector, m, None)
    cap = cv2.VideoCapture(str(v))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    pipe, rows, i = None, [], 0
    while True:
        if i % STEP:
            if not cap.grab():
                break
            i += 1
            continue
        ok, fr = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        if pipe is None:
            pipe = DistractionPipeline(copy.deepcopy(pcfg), rcfg, (g.shape[1], g.shape[0]),
                                       detector=det)
        r = pipe.process(g, i / fps)
        rows.append({"t": round(i / fps, 3), "face": r.face is not None,
                     "boxes": [[d.cls, round(d.conf, 3)] for d in r.detections],
                     "levels": {b: st["level"] for b, st in r.behaviours.items()}})
        i += 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"video": v.name, "frames": rows}), encoding="utf8")
    return str(out)


if __name__ == "__main__":
    vids = [str(p) for p in sorted(ROOT.rglob("*.mp4"))
            if re.sub(r"\s+", "", p.stem).upper().split("_")[0] in ("AKKAS", "JEWEL")]
    print(len(vids), "videos", flush=True)
    with ProcessPoolExecutor(5) as ex:
        for r in ex.map(run, vids):
            print(r, flush=True)
