"""v2 step 6: full-pipeline latency of the hybrid on this PC's CPU, per frame, on real frames.

Stages (all CPU, NCNN 4 threads where it applies):
  release pipeline  = face mesh + det_v2d INT8 (ACIQ mixed, the Pi model) 512 + simple rules,
                      timed per stage by the pipeline itself;
  crops             = upper-body 224 + 2 ear 128 + lap 128 cut from the frame, contrast stretch;
  action            = act_n224 INT8 KL NCNN;
  ear phone x2      = phone_n128 INT8 KL NCNN (only needed while the action says call);
  lap phone         = phone_lap_n128 INT8 KL NCNN (only needed while the action says texting).
Pi 5 estimate: CPU stages x (45 ms / det_v2d PC ms) (det_v2d measured on the Pi at ~45 ms);
face mesh = 4.4 ms measured on the Pi. Worst case = every model on every frame.

python bench_v2.py [n_frames=300] [detect_every=1]
"""
import copy
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
EXP = Path(r"C:\Users\youss\projects\RTDMS\models\distraction\experiments")
sys.path.insert(0, str(EXP))
import _paths  # noqa: E402,F401

from extract import crops  # noqa: E402

A = Path("D:/rtdms-data/action_v1")
W = A / "runs"
MODELS = {"action": (W / "act_n224/weights/best_int8kl_ncnn_model", 224),
          "phone_ear": (W / "phone_n128/weights/best_int8kl_ncnn_model", 128),
          "phone_lap": (W / "phone_lap_n128/weights/best_int8kl_ncnn_model", 128)}
PI_DET_MS, PI_FACE_MS = 45.0, 4.4


class Ncnn:
    def __init__(self, d, size, threads=4):
        import ncnn
        self.ncnn = ncnn
        self.net = ncnn.Net()
        self.net.opt.num_threads = threads
        self.net.load_param(str(Path(d) / "model.ncnn.param"))
        self.net.load_model(str(Path(d) / "model.ncnn.bin"))
        self.size = size
        self.inp, self.out = self.net.input_names()[0], self.net.output_names()[0]

    def __call__(self, gray):
        x = cv2.resize(gray, (self.size, self.size)).astype(np.float32) / 255.0
        x = np.ascontiguousarray(np.repeat(x[None], 3, 0))
        ex = self.net.create_extractor()
        ex.input(self.inp, self.ncnn.Mat(x))
        return np.array(ex.extract(self.out)[1])


def frames(n):
    """Real driver frames: 3MDAD test (640x480) - same size class as the Pi camera view."""
    root = Path("D:/rtdms-data/raw/3mdad/front/Day-RGB2/RGB2")
    fs = sorted(root.glob("S3/AC*/*.jpg"))[:: 3][:n]
    return [cv2.imread(str(f), cv2.IMREAD_GRAYSCALE) for f in fs]


def main():
    import os
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    every = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    os.chdir(_paths.REPO)
    from live import build_detector
    from rtdms_distraction.config import LiveModel, load_pipeline_config, load_rules_config
    from rtdms_distraction.pipeline import DistractionPipeline

    pcfg, rcfg = load_pipeline_config(profile="laptop_webcam"), load_rules_config()
    rcfg.mode = "simple"
    rcfg.simple.texting = False
    pcfg.detector.conf = {"phone": .40, "drink": .45, "food": .40}
    pcfg.detector.num_threads = 4
    pcfg.detector.every_n = every
    m = LiveModel(name="det_v2d", weights="models/det_v2d_ir_512_det_aciq_mixed_ncnn_model",
                  imgsz=512, hands="mediapipe")
    det = build_detector(pcfg.detector, m, None)
    nets = {k: Ncnn(d, s) for k, (d, s) in MODELS.items()}
    fr = frames(n)
    pipe = DistractionPipeline(copy.deepcopy(pcfg), rcfg, (fr[0].shape[1], fr[0].shape[0]),
                               detector=det)
    st = {k: [] for k in ("detect", "facemesh", "rules", "release_total", "crops", "action",
                          "phone_ear_x2", "phone_lap", "hybrid_total")}
    for i, g in enumerate(fr * 2):  # second pass = warm
        t0 = time.perf_counter()
        r = pipe.process(g, i / 10.0)
        t1 = time.perf_counter()
        rec = {"release_total": (t1 - t0) * 1000,
               **{k: r.timings_ms.get(k, 0.0) for k in ("detect", "facemesh", "rules")}}
        if r.face is not None:
            lm = r.face.full_landmarks if hasattr(r.face, "full_landmarks") else r.face.landmarks
            t2 = time.perf_counter()
            up, er, el, lap, _, _ = crops(g, np.asarray(lm, np.float64))
            t3 = time.perf_counter()
            nets["action"](up)
            t4 = time.perf_counter()
            nets["phone_ear"](er)
            nets["phone_ear"](el)
            t5 = time.perf_counter()
            nets["phone_lap"](lap)
            t6 = time.perf_counter()
            rec.update(crops=(t3 - t2) * 1000, action=(t4 - t3) * 1000,
                       phone_ear_x2=(t5 - t4) * 1000, phone_lap=(t6 - t5) * 1000)
            rec["hybrid_total"] = rec["release_total"] + (t6 - t2) * 1000
        if i >= len(fr):
            for k, v in rec.items():
                st[k].append(v)
    med = {k: round(float(np.mean(v)), 2) for k, v in st.items() if v}
    det_run = float(np.mean([v for v in st["detect"] if v > 0.5])) if st["detect"] else 0
    scale = PI_DET_MS / det_run if det_run else None
    pc_face = med.get("facemesh", 0.0)
    pi = {}
    if scale:
        cpu = {k: med[k] * scale for k in ("detect", "rules", "crops", "action", "phone_ear_x2",
                                          "phone_lap") if k in med}
        pi = {k: round(v, 1) for k, v in cpu.items()}
        pi["facemesh"] = PI_FACE_MS
        worst = sum(pi.values())
        typical = worst - 0.7 * (pi.get("phone_ear_x2", 0) + pi.get("phone_lap", 0))
        pi["worst_total_ms"] = round(worst, 1)
        pi["worst_fps"] = round(1000 / worst, 1)
        pi["typical_total_ms"] = round(typical, 1)
        pi["typical_fps"] = round(1000 / typical, 1)
    res = {"frames": len(fr), "detect_every": every, "pc_cpu_mean_ms": med,
           "pc_detect_ms_when_run": round(det_run, 2), "pc_facemesh_ms": pc_face,
           "pi5_scale_cpu": round(scale, 2) if scale else None, "pi5_est_ms": pi,
           "pc_fps_hybrid": round(1000 / med["hybrid_total"], 1) if "hybrid_total" in med else None,
           "note": "typical = phone checks run on ~30% of frames (only while the action says call "
                   "or texting); worst = every model on every frame."}
    out = A / "runs" / f"bench_v2_every{every}.json"
    out.write_text(json.dumps(res, indent=1), encoding="utf8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
