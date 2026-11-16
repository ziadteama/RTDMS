"""IR step 2.3: phone-in-hand hard negatives from SynDD TRAIN drivers (rear view, monochrome).

For every phone segment (phone_right_ear, phone_left_ear, phone_in_hand) of a train driver,
sample 3 fps, take the cached face mesh (eval_cache/faces/fps10, 640-wide coordinates), run the
release NCNN pose on the 640-wide view, and keep the frame if the hand point is within K=1.25
face heights of the mouth (same gate + crop as the product: held_runtime). Crops are cut from the
full-resolution frame (as the training crops) and written as empty_hand negatives.
Cigarette negatives already exist (3MDAD AC16 smoking crops are in empty_hand); SynDD has no
smoking class.

python ir_hardneg.py   -> _held_data/ir/hardneg/{train/empty_hand/*.jpg, manifest.csv}
"""

import csv
import importlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "src")]
OUT = HERE.parent / "_held_data/ir/hardneg"
PHONE = {"phone_right_ear", "phone_left_ear", "phone_in_hand"}
FACES = Path("D:/rtdms-data/eval_cache/faces/fps10")


def work(job):
    from held_runtime import K, hand_geometry, pose_mouth, square_cover

    from ultralytics import YOLO

    fit = json.loads((HERE.parent / "_held_data/geometry_v2/mouth_fit.json").read_text())
    # PyTorch yolo26n-pose at 320 (the NCNN export's source model; ncnn is blocked by Windows
    # Application Control on this PC since 2026-11-14 afternoon). Same driver choice as
    # rtdms_distraction.pose.driver_person: person box containing the face, else best score.
    pose = YOLO(str(HERE.parents[1] / "models/yolo26n-pose.pt"))

    def driver_kp(view_bgr, face_center):
        r = pose(view_bgr, imgsz=320, verbose=False, device="cpu")[0]
        if r.keypoints is None or len(r.boxes) == 0:
            return None
        boxes, scores = r.boxes.xyxy.numpy(), r.boxes.conf.numpy()
        kps = r.keypoints.data.numpy()
        idx = list(range(len(boxes)))
        if face_center is not None:
            inside = [i for i in idx if boxes[i, 0] <= face_center[0] <= boxes[i, 2]
                      and boxes[i, 1] <= face_center[1] <= boxes[i, 3]]
            idx = inside or idx
        return kps[max(idx, key=lambda i: scores[i])]

    z = np.load(FACES / f"{job['clip']}.npz")
    faces = {round(float(t), 1): (bool(o), lm) for t, o, lm in zip(z["t"], z["ok"], z["lm"], strict=True)}
    cap = cv2.VideoCapture(job["src"])
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    rows = []
    dest = OUT / "train/empty_hand"
    dest.mkdir(parents=True, exist_ok=True)
    for c in job["intervals"]:
        if c["label"] not in PHONE:
            continue
        for t in np.arange(c["s"], c["e"], 1 / 3):
            cap.set(cv2.CAP_PROP_POS_FRAMES, round(t * fps))
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            scale = width / 640
            view = cv2.resize(gray, (640, round(gray.shape[0] / scale)))
            entry = faces.get(round(float(t), 1))
            lm = entry[1] if entry and entry[0] else None
            kp = driver_kp(cv2.cvtColor(view, cv2.COLOR_GRAY2BGR),
                           None if lm is None else (lm[10] + lm[152]) / 2)
            if kp is None:
                continue
            if lm is not None:
                mouth, fh = (lm[13] + lm[14]) / 2, float(np.linalg.norm(lm[10] - lm[152]))
            else:
                got = pose_mouth(kp, fit)
                if got is None:
                    continue
                mouth, fh = got
            if fh <= 1:
                continue
            d, crop = hand_geometry(kp, np.asarray(mouth), fh)
            if d is None or d > K:
                continue
            center, side = crop
            img = square_cover(gray, np.asarray(center) * scale, side * scale)
            name = f"syndd_{job['clip']}_{c['label']}_{t:07.1f}.jpg"
            cv2.imwrite(str(dest / name), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            rows.append(dict(path=f"train/empty_hand/{name}", dataset="syndd", driver=job["driver"],
                             clip=job["clip"], t=round(float(t), 2), label=c["label"],
                             target="empty_hand", source="phone hard negative", dist=round(d, 3)))
    cap.release()
    return rows


def main():
    b = importlib.import_module("phase_b")
    jobs = [j for j in b.windows("train") if any(c["label"] in PHONE for c in j["intervals"])]
    jobs = [dict(clip=j["clip"], src=j["src"], driver=j["driver"],
                 intervals=[c for c in j["intervals"] if c["label"] in PHONE]) for j in jobs]
    z = np.load(FACES / f"{jobs[0]['clip']}.npz")
    assert float(np.nanmax(z["lm"][z["ok"]][..., 0])) < 700, "faces cache is not 640-wide"
    rows = []
    # One process: Windows Application Control blocked the ncnn DLL inside pool workers.
    for i, job in enumerate(jobs):
        rows += work(job)
        print(f"[hardneg] {i + 1}/{len(jobs)} videos, {len(rows)} crops", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "manifest.csv", "w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    by = {}
    for r in rows:
        by[r["label"]] = by.get(r["label"], 0) + 1
    print("[hardneg] done", len(rows), by, "drivers", len({r["driver"] for r in rows}))


if __name__ == "__main__":
    main()
