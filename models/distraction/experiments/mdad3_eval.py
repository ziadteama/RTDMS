"""Unseen-data test: 3MDAD front view (day, Kinect RGB -> gray), 50 drivers never used in training.
Each clip runs through the live simple-mode pipeline (deployed NCNN det_v2d, phone .40 drink .45,
face mesh for the lower-face zone) with a fresh pipeline per clip. The frames are sparse, so time
is assumed to advance DT s per frame; per-frame numbers do not depend on that.
python mdad3_eval.py run [workers] | python mdad3_eval.py summary"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import copy
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(f"{DATA}/raw/3mdad/front/Day-RGB2/RGB2")
import os  # noqa: E402
MODEL = os.environ.get("RTDMS_MODEL", "det_v2d")
MODELS = {"det_v2d": ("models/det_v2d_ir_512_ncnn_model", 512, {"phone": .40, "drink": .45, "food": .40}),
          "det_v2h": ("models/det_v2h_fish_512_ncnn_model", 512, {"phone": .35, "drink": .55, "food": .40})}
OUT = Path(f"{DATA}/runs/unseen_3mdad") / ("" if MODEL == "det_v2d" else MODEL)
DT = 1 / 3  # assumed seconds per stored frame
ACTIONS = {1: "normal", 2: "hair_makeup", 3: "adjust_radio", 4: "gps", 5: "texting_right",
           6: "texting_left", 7: "phone_right_ear", 8: "phone_left_ear", 10: "talking_passenger",
           11: "singing", 13: "drinking_right", 14: "drinking_left", 16: "smoking"}


def frames(d: Path):
    def num(p):
        m = re.search(r"F(\d+)\.", p.name)
        return int(m.group(1)) if m else 0
    return sorted(d.glob("*.jpg"), key=num)


def run_clip(args):
    s, a = args
    out = OUT / "clips" / f"S{s}_AC{a}.json"
    if out.is_file():
        return str(out)
    from live import build_detector
    from rtdms_distraction.config import load_pipeline_config, load_rules_config
    from rtdms_distraction.pipeline import DistractionPipeline

    fs = frames(ROOT / f"S{s}" / f"AC{a}")
    rows = []
    if fs:
        pcfg, rcfg = load_pipeline_config(profile="laptop_webcam"), load_rules_config()
        rcfg.mode = "simple"
        rcfg.simple.texting = False  # needs a 10 s per-driver baseline before the action
        w, sz, conf = MODELS[MODEL]
        pcfg.detector.conf = dict(conf)
        from rtdms_distraction.config import LiveModel
        m = LiveModel(name=MODEL, weights=w, imgsz=sz, hands="mediapipe")
        det = build_detector(pcfg.detector, m, None)
        pipe = None
        for i, p in enumerate(fs):
            img = cv2.imread(str(p))
            if img is None:
                continue
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if pipe is None:
                pipe = DistractionPipeline(copy.deepcopy(pcfg), rcfg, (g.shape[1], g.shape[0]),
                                           detector=det)
            r = pipe.process(g, i * DT)
            rows.append({"i": i, "face": r.face is not None,
                         "boxes": [[d.cls, round(d.conf, 3)] for d in r.detections],
                         "levels": {b: st["level"] for b, st in r.behaviours.items()}})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"subject": s, "action": a, "label": ACTIONS[a], "frames": rows}),
                   encoding="utf8")
    return str(out)


def summary():
    by = {}
    for f in sorted((OUT / "clips").glob("*.json")):
        c = json.loads(f.read_text(encoding="utf8"))
        fr = c["frames"]
        if not fr:
            continue
        phone_f = np.mean([any(b[0] == "phone" for b in r["boxes"]) for r in fr])
        drink_f = np.mean([any(b[0] == "drink" for b in r["boxes"]) for r in fr])
        face_f = np.mean([r["face"] for r in fr])
        al = {b: any(r["levels"].get(b) == "alert" for r in fr) for b in ("phone", "drinking", "eating")}
        by.setdefault(c["label"], []).append({"s": c["subject"], "phone_f": phone_f, "drink_f": drink_f,
                                              "face_f": face_f, **{f"alert_{k}": v for k, v in al.items()}})
    res = {}
    for lab, rows in by.items():
        res[lab] = {"clips": len(rows),
                    "frames_with_phone_box": round(float(np.mean([r["phone_f"] for r in rows])), 3),
                    "frames_with_drink_box": round(float(np.mean([r["drink_f"] for r in rows])), 3),
                    "frames_with_face": round(float(np.mean([r["face_f"] for r in rows])), 3),
                    "clips_phone_alert": round(float(np.mean([r["alert_phone"] for r in rows])), 3),
                    "clips_drink_alert": round(float(np.mean([r["alert_drinking"] for r in rows])), 3),
                    "clips_eating_alert": round(float(np.mean([r["alert_eating"] for r in rows])), 3)}
        # driver bootstrap 5-95 % for the clip alert rate that matters for this action
        key = "alert_drinking" if lab.startswith("drinking") else "alert_phone"
        v = np.array([r[key] for r in rows], float)
        rng = np.random.default_rng(0)
        bs = [rng.choice(v, len(v)).mean() for _ in range(1000)]
        res[lab]["range_5_95"] = [round(float(np.percentile(bs, 5)), 2), round(float(np.percentile(bs, 95)), 2)]
    (OUT / "summary.json").write_text(json.dumps(res, indent=1), encoding="utf8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "run":
        jobs = [(s, a) for s in range(1, 51) for a in ACTIONS]
        with ProcessPoolExecutor(int(sys.argv[2]) if len(sys.argv) > 2 else 4) as ex:
            for k, o in enumerate(ex.map(run_clip, jobs), 1):
                if k % 50 == 0:
                    print(k, len(jobs), flush=True)
        summary()
    else:
        summary()
