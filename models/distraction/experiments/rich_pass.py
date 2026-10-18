"""Cache for rules A / B: per frame (10 fps, live geometry) face pitch / yaw / gaze / jaw / lips +
landmarks, and the driver's pose keypoints (yolo26n-pose @320).
python rich_pass.py <split> [drivers comma list]"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

import eval_simple as E  # noqa: E402
from rtdms_distraction import datasets as D  # noqa: E402

OUT = Path(f"{DATA}/eval_cache/rich/fps10")
POSE_W = str(REPO / "models/yolo26n-pose.pt")


def run(video: str) -> str:
    out = OUT / f"{Path(video).stem}.npz"
    if out.is_file():
        return str(out)
    from ultralytics import YOLO

    from rtdms_distraction.config import load_pipeline_config
    from rtdms_distraction.facemesh import FaceMesh

    pcfg = load_pipeline_config(profile="laptop_webcam")
    pose = YOLO(POSE_W)
    mesh = None
    T, ok, lm, pitch, yaw, gaze, gsrc, jaw, jsrc, lip, kp = ([] for _ in range(11))
    for t, view in E.frames(Path(video), 10.0):
        if mesh is None:
            h, w = view.shape[:2]
            mesh = FaceMesh(pcfg.facemesh, w, h, np.array([[w, 0, w / 2], [0, w, h / 2],
                                                          [0, 0, 1.0]]))
        f = mesh.process(cv2.cvtColor(view, cv2.COLOR_BGR2RGB), t)
        T.append(t)
        ok.append(f is not None)
        nan = float("nan")
        lm.append(f.landmarks[:, :2].astype(np.float32) if f else np.zeros((478, 2), np.float32))
        pitch.append(f.pitch_deg if f and f.pitch_deg is not None else nan)
        yaw.append(f.yaw_deg if f and f.yaw_deg is not None else nan)
        gaze.append(f.gaze_down if f and f.gaze_down is not None else nan)
        gsrc.append(f.gaze_source if f else "none")
        jaw.append(f.jaw_open if f and f.jaw_open is not None else nan)
        jsrc.append(f.jaw_source if f else "none")
        lip.append(f.lip_ratio if f else nan)
        r = pose.predict(view, imgsz=320, conf=0.3, verbose=False)[0]
        k = np.full((17, 3), np.nan, np.float32)
        if len(r.boxes):
            b = r.boxes.xyxy.cpu().numpy()
            kk = r.keypoints.data.cpu().numpy()
            i = int(np.argmax((b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])))
            if f is not None:  # the person whose box holds the face, like pose.driver_person
                fx, fy = f.landmarks[1, :2]
                inside = [j for j in range(len(b)) if b[j, 0] <= fx <= b[j, 2] and
                          b[j, 1] <= fy <= b[j, 3]]
                if inside:
                    i = max(inside, key=lambda j: float(r.boxes.conf[j]))
            k = kk[i].astype(np.float32)
        kp.append(k)
    if mesh is not None:
        mesh.close()
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, t=np.array(T), ok=np.array(ok), lm=np.array(lm),
                        pitch=np.array(pitch), yaw=np.array(yaw), gaze=np.array(gaze),
                        gsrc=np.array(gsrc), jaw=np.array(jaw), jsrc=np.array(jsrc),
                        lip=np.array(lip), kp=np.array(kp))
    return str(out)


if __name__ == "__main__":
    split_name = sys.argv[1]
    drivers = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
    split = json.load(open(str(REPO / "configs/syndd_split.json")))
    segs = [s for s in D.syndd(f"{DATA}/public/syndd/A1") if split.get(s.driver) == split_name
            and (drivers is None or s.driver in drivers)]
    videos = sorted({str(s.video) for s in segs})
    with ProcessPoolExecutor(4) as ex:
        for i, o in enumerate(ex.map(run, videos), 1):
            print(f"[{i}/{len(videos)}] {Path(o).name}", flush=True)
