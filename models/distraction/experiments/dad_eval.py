"""Unseen real-IR test: DAD (TU Munich), drivers Tester1 / 10 / 11 (part 1 of the archive).
Each clip / normal-driving video goes through the live simple-mode pipeline (deployed NCNN
det_v2d, phone .40 drink .45), every 4th frame of 45 fps (11.25 fps), time = frame / 45.
Cameras: front_IR (driver's face / upper body) and top_IR (hands, from above).
python dad_eval.py run [workers] | python dad_eval.py summary"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import copy
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(f"{DATA}/raw/dad/x/DAD")
import os  # noqa: E402
MODEL = os.environ.get("RTDMS_MODEL", "det_v2d")
MODELS = {"det_v2d": ("models/det_v2d_ir_512_ncnn_model", 512, {"phone": .40, "drink": .45, "food": .40}),
          "det_v2h": ("models/det_v2h_fish_512_ncnn_model", 512, {"phone": .35, "drink": .55, "food": .40})}
OUT = Path(f"{DATA}/runs/unseen_dad") / ("" if MODEL == "det_v2d" else MODEL)
STEP, FPS = 4, 45.0


def jobs():
    out = []
    for t in sorted(ROOT.glob("Tester*")):
        for a in sorted(t.iterdir()):
            for v in ("front_IR", "top_IR"):
                if (a / v).is_dir():
                    out.append((t.name, a.name, v))
    return out


def run(job):
    tester, action, view = job
    out = OUT / "clips" / f"{tester}__{action}__{view}.json"
    if out.is_file():
        return str(out)
    from live import build_detector
    from rtdms_distraction.config import load_pipeline_config, load_rules_config
    from rtdms_distraction.pipeline import DistractionPipeline

    d = ROOT / tester / action / view
    idx = sorted(int(re.search(r"img_(\d+)", p.name).group(1)) for p in d.glob("img_*.png"))
    pcfg, rcfg = load_pipeline_config(profile="laptop_webcam"), load_rules_config()
    rcfg.mode = "simple"
    rcfg.simple.texting = False  # clips start mid-action: no per-driver baseline
    w, sz, conf = MODELS[MODEL]
    pcfg.detector.conf = dict(conf)
    from rtdms_distraction.config import LiveModel
    m = LiveModel(name=MODEL, weights=w, imgsz=sz, hands="mediapipe")
    det = build_detector(pcfg.detector, m, None)
    pipe, rows = None, []
    for i in idx[::STEP]:
        g = cv2.imread(str(d / f"img_{i}.png"), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        if pipe is None:
            pipe = DistractionPipeline(copy.deepcopy(pcfg), rcfg, (g.shape[1], g.shape[0]),
                                       detector=det)
        r = pipe.process(g, i / FPS)
        rows.append({"t": round(i / FPS, 3), "face": r.face is not None,
                     "boxes": [[x.cls, round(x.conf, 3)] for x in r.detections],
                     "levels": {b: st["level"] for b, st in r.behaviours.items()}})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"tester": tester, "action": action, "view": view, "frames": rows}),
                   encoding="utf8")
    return str(out)


def onsets(rows, b):
    n, prev = 0, False
    for r in rows:
        on = r["levels"].get(b) == "alert"
        n += on and not prev
        prev = on
    return n


def summary():
    res = {}
    for f in sorted((OUT / "clips").glob("*.json")):
        c = json.loads(f.read_text(encoding="utf8"))
        fr = c["frames"]
        if not fr:
            continue
        act = "normal_driving" if c["action"].startswith("normal") else c["action"]
        e = res.setdefault(c["view"], {}).setdefault(act, {"clips": 0, "phone_alert": 0,
                                                          "drink_alert": 0, "phone_onsets": 0,
                                                          "drink_onsets": 0, "seconds": 0.0,
                                                          "phone_frames": 0.0, "drink_frames": 0.0,
                                                          "face_frames": 0.0, "per_tester": {}})
        pa = any(r["levels"].get("phone") == "alert" for r in fr)
        da = any(r["levels"].get("drinking") == "alert" for r in fr)
        e["clips"] += 1
        e["phone_alert"] += pa
        e["drink_alert"] += da
        e["phone_onsets"] += onsets(fr, "phone")
        e["drink_onsets"] += onsets(fr, "drinking")
        e["seconds"] += fr[-1]["t"] - fr[0]["t"]
        e["phone_frames"] += np.mean([any(b[0] == "phone" for b in r["boxes"]) for r in fr])
        e["drink_frames"] += np.mean([any(b[0] == "drink" for b in r["boxes"]) for r in fr])
        e["face_frames"] += np.mean([r["face"] for r in fr])
        e["per_tester"][c["tester"] + ("" if act != "normal_driving" else "_" + c["action"][-1])] = \
            {"phone_alert": pa, "drink_alert": da}
    for v in res.values():
        for e in v.values():
            k = e["clips"]
            for x in ("phone_frames", "drink_frames", "face_frames"):
                e[x] = round(e[x] / k, 3)
            e["phone_FA_per_h"] = round(e["phone_onsets"] / (e["seconds"] / 3600), 1)
            e["drink_FA_per_h"] = round(e["drink_onsets"] / (e["seconds"] / 3600), 1)
            e["minutes"] = round(e["seconds"] / 60, 1)
    (OUT / "summary.json").write_text(json.dumps(res, indent=1), encoding="utf8")
    for view, v in res.items():
        print("==", view)
        for act, e in sorted(v.items()):
            print(f"  {act:24s} clips {e['clips']:2d}  phone alert {e['phone_alert']}/{e['clips']}  "
                  f"drink alert {e['drink_alert']}/{e['clips']}  phone-box frames {e['phone_frames']:.2f}  "
                  f"drink-box frames {e['drink_frames']:.2f}  face {e['face_frames']:.2f}  "
                  f"{e['minutes']} min  phone FA/h {e['phone_FA_per_h']}  drink FA/h {e['drink_FA_per_h']}")


if __name__ == "__main__":
    if sys.argv[1] == "run":
        js = jobs()
        print(len(js), "jobs", flush=True)
        with ProcessPoolExecutor(int(sys.argv[2]) if len(sys.argv) > 2 else 6) as ex:
            for k, o in enumerate(ex.map(run, js), 1):
                print(k, Path(o).name, flush=True)
        summary()
    else:
        summary()
