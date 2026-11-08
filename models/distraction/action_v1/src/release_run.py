"""v2: run the RELEASE pipeline (det_v2d NCNN, simple rules, phone .40 drink .45 food .40,
laptop_webcam profile, texting rule off - as in experiments/mdad3_eval.py and dad_eval.py) and keep
what the hybrid needs: every box WITH its coordinates, the face landmarks used by the rules and
the mouth (1, 10, 13, 14, 152, 234, 454), and the release alert levels.
Frame rates as the earlier release runs: 3MDAD every stored frame (t = i / 3), EBDD every 3rd
frame (10 fps), DAD every 4th of 45 fps. SynDD is not needed here (cached boxes + faces exist).

python release_run.py <3mdad|ebdd|dad> [workers]  -> runs/release_v2/<ds>/<clip>.json
"""
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

A = Path("D:/rtdms-data/action_v1")
DATA = Path("D:/rtdms-data")
OUT = A / "runs" / "release_v2"
LM_KEEP = (1, 10, 13, 14, 152, 234, 454)
MDAD_ACTIONS = (1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16)


def frames_3mdad(d):
    def num(p):
        m = re.search(r"F(\d+)\.", p.name)
        return int(m.group(1)) if m else 0
    for i, p in enumerate(sorted(Path(d).glob("*.jpg"), key=num)):
        yield i / 3.0, cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)


def frames_video(v, step=3):
    cap = cv2.VideoCapture(str(v))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    i = 0
    while True:
        if i % step:
            if not cap.grab():
                break
            i += 1
            continue
        ok, fr = cap.read()
        if not ok:
            break
        yield i / fps, cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        i += 1
    cap.release()


def frames_dad(d, step=4):
    idx = sorted(int(re.search(r"img_(\d+)", p.name).group(1)) for p in Path(d).glob("img_*.png"))
    for i in idx[::step]:
        yield i / 45.0, cv2.imread(str(Path(d) / f"img_{i}.png"), cv2.IMREAD_GRAYSCALE)


def jobs(ds):
    if ds == "3mdad":
        sp = json.load(open(A / "splits" / "3mdad.json"))
        root = DATA / "raw/3mdad/front/Day-RGB2/RGB2"
        return [(ds, f"S{s}_AC{a}", str(root / f"S{s}" / f"AC{a}")) for s in sp["test"]
                for a in MDAD_ACTIONS if (root / f"S{s}" / f"AC{a}").is_dir()]
    if ds == "ebdd":
        out = []
        for p in sorted((DATA / "raw/ebdd/x").rglob("*.mp4")):
            stem = re.sub(r"\s+", "", p.stem).upper()
            drv = stem.split("_")[0]
            if drv in ("AKKAS", "JEWEL"):
                key = stem[len(drv) + 1:]
                out.append((ds, f"ebdd_{drv.lower()}_{key}", str(p)))
        return out
    if ds == "dad":
        return [(ds, f"{d.parent.parent.name}_{d.parent.name}", str(d))
                for d in sorted((DATA / "raw/dad/x/DAD").glob("Tester*/*/front_IR"))]
    raise SystemExit(ds)


def run(job):
    import os
    ds, clip, src = job
    out = OUT / ds / f"{clip}.json"
    if out.exists():
        return str(out)
    os.chdir(_paths.REPO)
    from live import build_detector
    from rtdms_distraction.config import LiveModel, load_pipeline_config, load_rules_config
    from rtdms_distraction.pipeline import DistractionPipeline

    pcfg, rcfg = load_pipeline_config(profile="laptop_webcam"), load_rules_config()
    rcfg.mode = "simple"
    rcfg.simple.texting = False
    pcfg.detector.conf = {"phone": .40, "drink": .45, "food": .40}
    m = LiveModel(name="det_v2d", weights="models/det_v2d_ir_512_ncnn_model", imgsz=512,
                  hands="mediapipe")
    det = build_detector(pcfg.detector, m, None)
    gen = {"3mdad": frames_3mdad, "ebdd": frames_video, "dad": frames_dad}[ds](src)
    pipe, rows = None, []
    for t, g in gen:
        if g is None:
            continue
        if pipe is None:
            pipe = DistractionPipeline(copy.deepcopy(pcfg), rcfg, (g.shape[1], g.shape[0]),
                                       detector=det)
        r = pipe.process(g, t)
        lm = None
        if r.face is not None:
            lm = {str(k): [round(float(r.face.landmarks[k][0]), 1),
                           round(float(r.face.landmarks[k][1]), 1)] for k in LM_KEEP}
        rows.append({"t": round(t, 3), "lm": lm,
                     "dets": [[d.cls, round(d.conf, 3), round(d.box.x1, 1), round(d.box.y1, 1),
                               round(d.box.x2, 1), round(d.box.y2, 1)] for d in r.detections],
                     "levels": {b: st["level"] for b, st in r.behaviours.items()}})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"clip": clip, "frames": rows}), encoding="utf8")
    return str(out)


if __name__ == "__main__":
    ds = sys.argv[1]
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    js = jobs(ds)
    print(ds, len(js), "clips", flush=True)
    with ProcessPoolExecutor(workers) as ex:
        for k, r in enumerate(ex.map(run, js), 1):
            if k % 20 == 0 or k == len(js):
                print(f"  {k}/{len(js)}", flush=True)
