#!/usr/bin/env python3
"""Auto-label phone / drink / food BOXES on driver video (SynDD rear view, EBDD) with a large
teacher on a zoomed driver crop, keeping only boxes that agree with the segment label.
TRAINING ENV (GPU).

    python scripts/label_video_boxes.py syndd --src D:/rtdms-data/public/syndd/A1 \
        --split-file configs/syndd_split.json --out D:/rtdms-data/det_v2/syndd --workers 4
    python scripts/label_video_boxes.py ebdd --src D:/rtdms-data/raw/ebdd/x \
        --out D:/rtdms-data/det_v2/ebdd --workers 4

Per sampled frame:
  1. driver = largest person (yolo26m @640) -> padded crop, i.e. a ~2x zoom for the teacher;
  2. teacher yolo26m @1280 on the crop: cell phone -> phone, cup / bottle / wine glass -> drink,
     COCO foods -> food (eating segments also YOLO-World "food" prompts);
  3. face (MediaPipe face landmarker) for the label-agreement rules;
  4. keep boxes that agree with the segment label:
       phone_*_ear      phone centre within 1.6 fw of the face centre, eye line - 0.6 fw ..
                        chin + 0.8 fw vertically
       phone_in_hand    phone centre below the eye line
       drinking         any drink box (conf >= 0.3)
       eating           food box within 2 fw of the mouth
     A positive frame with no agreeing box is DROPPED (not written as background): the teacher
     misses heavily hidden phones, and "no box" would teach the student to miss them too.
     Other confident boxes (>= 0.5) of other classes are kept as well.
  5. negatives (normal, hand on head, yawning, talking, singing): written as background; phone
     boxes are removed (hand-on-head is where teachers hallucinate phones), but a frame with a
     confident phone (>= 0.5) is skipped as ambiguous (could be a phone in a holder).
Frames are stored at max side 960 (detector trains at 416). Split by driver.
Output: <out>/{images,labels}/{train,val,test}/*.jpg|txt (classes 0 phone, 1 drink, 2 food)
+ <out>/meta.csv (source, driver, label, frame, kept boxes with teacher confidences).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rtdms_distraction import datasets as D  # noqa: E402

PHONE, DRINK, FOOD = 0, 1, 2
COCO = {67: PHONE, 41: DRINK, 39: DRINK, 40: DRINK,
        46: FOOD, 47: FOOD, 48: FOOD, 49: FOOD, 52: FOOD, 53: FOOD, 54: FOOD, 55: FOOD}
FOOD_PROMPTS = ["food", "snack", "sandwich", "burger", "chips bag", "fruit", "cookie",
                "chocolate bar"]
POS = {"phone_right_ear", "phone_left_ear", "phone_unknown_ear", "phone_in_hand", "drinking",
       "eating"}
NEG = {"normal", "neg_hand_on_head", "neg_yawning", "neg_talking", "neg_singing", "other_none"}
EBDD_MAP = {"phone_unknown_ear": "phone_unknown_ear", "phone_in_hand": "phone_in_hand",
            "eating": "eating", "normal": "normal", "other_none": "other_none"}

_M: dict = {}


def _models():
    if not _M:
        import mediapipe as mp
        from mediapipe.tasks import python as mpp
        from mediapipe.tasks.python import vision
        from ultralytics import YOLO

        _M["person"] = YOLO("yolo26m-pose.pt")  # driver box + head keypoints (face fallback)
        _M["teacher"] = YOLO("yolo26m.pt")
        _M["mp"] = mp
        _M["face"] = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=str(
                (ROOT.parent / "face" / "models" / "face_landmarker.task").resolve())),
            running_mode=vision.RunningMode.IMAGE, num_faces=1))
    return _M


def _world():
    if "world" not in _M:
        from ultralytics import YOLOWorld

        w = YOLOWorld("yolov8l-worldv2.pt")
        w.set_classes(FOOD_PROMPTS)
        _M["world"] = w
    return _M["world"]


def driver_crop(frame, person_model, pad=0.12):
    """-> (crop box, head geometry from pose keypoints or None), driver = largest person."""
    h, w = frame.shape[:2]
    r = person_model.predict(frame, imgsz=640, conf=0.3, verbose=False)[0]
    if not len(r.boxes):
        return None, None
    b = r.boxes.xyxy.cpu().numpy()
    i = int(np.argmax((b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])))
    x1, y1, x2, y2 = b[i]
    pw, ph = x2 - x1, y2 - y1
    crop = (int(max(0, x1 - pad * pw)), int(max(0, y1 - pad * ph)),
            int(min(w, x2 + pad * pw)), int(min(h, y2 + pad * ph)))
    return crop, pose_head(r.keypoints.data[i].cpu().numpy())


def pose_head(k, min_conf=0.4):
    """COCO keypoints 0 nose, 1/2 eyes, 3/4 ears, 5/6 shoulders -> rough face geometry, used
    when the face mesh fails (a hand and phone over the face: ~35 % of SynDD phone calls)."""
    ok = k[:, 2] >= min_conf
    if not ok[0] and not (ok[1] or ok[2]):
        return None
    if ok[3] and ok[4]:
        fw = float(np.linalg.norm(k[3, :2] - k[4, :2]))
    elif ok[1] and ok[2]:
        fw = 2.2 * float(np.linalg.norm(k[1, :2] - k[2, :2]))
    elif ok[5] and ok[6]:
        fw = 0.45 * float(np.linalg.norm(k[5, :2] - k[6, :2]))
    else:
        return None
    eyes = [k[j, :2] for j in (1, 2) if ok[j]]
    eye_y = float(np.mean([e[1] for e in eyes])) if eyes else float(k[0, 1]) - 0.15 * fw
    nose = k[0, :2] if ok[0] else np.mean(eyes, axis=0) + np.array([0, 0.25 * fw])
    return {"center": nose.copy(), "eye_y": eye_y, "chin_y": float(nose[1]) + 0.55 * fw,
            "mouth": nose + np.array([0, 0.3 * fw]), "fw": fw, "src": "pose"}


def face_geom(frame, m):
    mp = m["mp"]
    res = m["face"].detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                    data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    if not res.face_landmarks:
        return None
    h, w = frame.shape[:2]
    lm = np.array([(q.x * w, q.y * h) for q in res.face_landmarks[0]])
    fw = float(np.linalg.norm(lm[234] - lm[454]))
    return {"center": lm[[1, 152]].mean(0), "eye_y": float(lm[[33, 263], 1].mean()),
            "chin_y": float(lm[152, 1]), "mouth": lm[[13, 14, 61, 291]].mean(0), "fw": fw,
            "src": "mesh"}


def _iou(a, b):
    ix = max(0.0, min(a[4], b[4]) - max(a[2], b[2]))
    iy = max(0.0, min(a[5], b[5]) - max(a[3], b[3]))
    inter = ix * iy
    ua = (a[4] - a[2]) * (a[5] - a[3]) + (b[4] - b[2]) * (b[5] - b[3]) - inter
    return inter / ua if ua > 0 else 0.0


FACE_PASS = {PHONE: ([67], 2.0), DRINK: ([39, 40, 41], 2.6)}  # COCO classes, half-size in fw


def teacher_boxes(frame, crop, m, with_food_world, face=None, face_cls=None):
    """Driver crop @1280 (all classes); with `face` and `face_cls`, also a tight face crop
    (~2x zoom) @640 with TTA and conf 0.15 for that class: on SynDD phone calls that finds the
    phone in 80 % of frames vs 63 % for the plain pass (the face rules keep it precise)."""
    x0, y0, x1, y1 = crop
    sub = frame[y0:y1, x0:x1]
    out = []
    r = m["teacher"].predict(sub, imgsz=1280, conf=0.25, classes=list(COCO), verbose=False)[0]
    for (a, b, c, d), cls, cf in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.cls.cpu().numpy(),
                                     r.boxes.conf.cpu().numpy(), strict=True):
        out.append((COCO[int(cls)], float(cf), a + x0, b + y0, c + x0, d + y0, "yolo26m"))
    if face is not None and face_cls in FACE_PASS:
        coco_ids, half = FACE_PASS[face_cls]
        h, w = frame.shape[:2]
        s = half * face["fw"]
        cx, cy = face["center"]
        fx0, fy0 = int(max(0, cx - s)), int(max(0, cy - s))
        fx1, fy1 = int(min(w, cx + s)), int(min(h, cy + s))
        if fx1 - fx0 > 16 and fy1 - fy0 > 16:
            r = m["teacher"].predict(frame[fy0:fy1, fx0:fx1], imgsz=640, conf=0.15,
                                     classes=coco_ids, augment=True, verbose=False)[0]
            for (a, b, c, d), cf in zip(r.boxes.xyxy.cpu().numpy(),
                                        r.boxes.conf.cpu().numpy(), strict=True):
                bx = (face_cls, float(cf), a + fx0, b + fy0, c + fx0, d + fy0, "yolo26m_face")
                dup = [o for o in out if o[0] == face_cls and _iou(o, bx) > 0.5]
                if not dup:
                    out.append(bx)
    if with_food_world:
        r = _world().predict(sub, imgsz=640, conf=0.15, verbose=False)[0]
        for (a, b, c, d), cf in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(),
                                    strict=True):
            out.append((FOOD, float(cf), a + x0, b + y0, c + x0, d + y0, "yoloworld"))
    return out


def agree(label, boxes, face):
    """-> (kept boxes, keep_frame)."""
    ctr = lambda b: ((b[2] + b[4]) / 2, (b[3] + b[5]) / 2)  # noqa: E731
    if label in NEG:
        if any(b[0] == PHONE and b[1] >= 0.5 for b in boxes):
            return [], False
        return dedupe([b for b in boxes if b[0] != PHONE and b[1] >= 0.5]), True
    want = PHONE if label.startswith("phone") else DRINK if label == "drinking" else FOOD
    good = []
    for b in boxes:
        if b[0] != want:
            continue
        cx, cy = ctr(b)
        if want == PHONE and label != "phone_in_hand":
            if face is None:
                continue
            fw = face["fw"]
            if (abs(cx - face["center"][0]) <= 1.6 * fw and
                    face["eye_y"] - 0.6 * fw <= cy <= face["chin_y"] + 0.8 * fw):
                good.append(b)
        elif want == PHONE:
            if face is None or cy > face["eye_y"]:
                good.append(b)
        elif want == DRINK:  # confident anywhere, or a weaker box near the mouth
            near = face is not None and np.hypot(cx - face["mouth"][0], cy - face["mouth"][1]) \
                <= 1.5 * face["fw"]
            if b[1] >= 0.3 or near:
                good.append(b)
        else:  # food near the mouth
            if face is not None and np.hypot(cx - face["mouth"][0], cy - face["mouth"][1]) <= \
                    2.0 * face["fw"]:
                good.append(b)
    if not good:
        return [], False
    others = [b for b in boxes if b[0] != want and b[0] != PHONE and b[1] >= 0.5]
    return dedupe(good + others), True


def _area(b):
    return max(0.0, b[4] - b[2]) * max(0.0, b[5] - b[3])


def _inside(a, b):
    """Fraction of box a inside box b."""
    ix = max(0.0, min(a[4], b[4]) - max(a[2], b[2]))
    iy = max(0.0, min(a[5], b[5]) - max(a[3], b[3]))
    return ix * iy / _area(a) if _area(a) > 0 else 0.0


def dedupe(boxes):
    """One driver holds one phone: keep the most confident phone box. Drink / food: greedy
    NMS by confidence, also dropping boxes mostly inside a kept one (the face-crop and driver-
    crop passes and TTA give nested duplicates, some covering the hand or face)."""
    phones = [b for b in boxes if b[0] == PHONE]
    kept = []
    if phones:
        best = max(phones, key=lambda b: b[1])
        # A loose box around hand + phone + cheek would teach "hand at face = phone": prefer a
        # tighter phone box inside it when its confidence is comparable.
        inner = [b for b in phones if b is not best and b[1] >= 0.6 * best[1] and
                 _inside(b, best) > 0.7 and 0.2 * _area(best) <= _area(b) < 0.6 * _area(best)]
        kept = [min(inner, key=_area) if inner else best]
    for b in sorted((b for b in boxes if b[0] != PHONE), key=lambda b: -b[1]):
        area = (b[4] - b[2]) * (b[5] - b[3])
        clash = False
        for k in kept:
            if k[0] != b[0]:
                continue
            ix = max(0.0, min(k[4], b[4]) - max(k[2], b[2]))
            iy = max(0.0, min(k[5], b[5]) - max(k[3], b[3]))
            small = min(area, (k[4] - k[2]) * (k[5] - k[3]))
            if _iou(k, b) > 0.4 or (small > 0 and ix * iy / small > 0.6):
                clash = True
                break
        if not clash:
            kept.append(b)
    return kept


def label_clip(clip: D.Clip, split: str, out: str, every_pos: float, every_neg: float,
               seed: int) -> list[dict]:
    m = _models()
    outp = Path(out)
    every = every_pos if clip.label in POS else every_neg
    rows = []
    for t, frame in clip.frames(every):
        crop, head = driver_crop(frame, m["person"])
        if crop is None:
            continue
        sub = frame[crop[1]:crop[3], crop[0]:crop[2]]
        face = face_geom(sub, m)
        if face is not None:  # back to frame coordinates
            for k in ("center", "mouth"):
                face[k] = face[k] + np.array(crop[:2])
            face["eye_y"] += crop[1]
            face["chin_y"] += crop[1]
        else:
            face = head  # pose keypoints (already in frame coordinates) or None
        face_cls = PHONE if clip.label in ("phone_right_ear", "phone_left_ear",
                                           "phone_unknown_ear") else \
            DRINK if clip.label == "drinking" else None
        boxes = teacher_boxes(frame, crop, m, clip.label == "eating", face, face_cls)
        kept, keep = agree(clip.label, boxes, face)
        if not keep:
            continue
        h, w = frame.shape[:2]
        s = 960 / max(h, w)
        img = cv2.resize(frame, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
        stem = f"{clip.source}__{clip.driver}__{Path(clip.name).stem}_{int(t * 1000):07d}"
        (outp / "images" / split).mkdir(parents=True, exist_ok=True)
        (outp / "labels" / split).mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(outp / "images" / split / f"{stem}.jpg"), img,
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        lines = [f"{c} {(a + c2) / 2 / w:.6f} {(b + d) / 2 / h:.6f} {(c2 - a) / w:.6f} "
                 f"{(d - b) / h:.6f}" for c, _, a, b, c2, d, _ in kept]
        (outp / "labels" / split / f"{stem}.txt").write_text("\n".join(lines) + "\n" if lines
                                                             else "", encoding="utf8")
        rows.append({"split": split, "source": clip.source, "driver": clip.driver,
                     "label": clip.label, "image": f"{split}/{stem}.jpg",
                     "boxes": json.dumps([[c, round(cf, 3), src] for c, cf, *_, src in kept])})
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("dataset", choices=["syndd", "ebdd"])
    p.add_argument("--src", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--split-file", help="JSON {driver: split}; else a seeded 70/15/15 split")
    p.add_argument("--every-pos", type=float, default=0.5)
    p.add_argument("--every-neg", type=float, default=1.5)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--drivers", help="comma list (smoke test)")
    p.add_argument("--limit", type=int, help="clips (smoke test)")
    p.add_argument("--view", default="rear", choices=["rear", "dash", "right"],
                   help="SynDD camera view (rear = mirror, the deployment view)")
    args = p.parse_args()

    if args.dataset == "syndd":
        clips = [c for c in D.syndd_clips(args.src, view=args.view) if c.label in POS | NEG]
    else:
        clips = [c for c in D.ebdd(args.src) if c.label in EBDD_MAP]
    if args.drivers:
        keep = set(args.drivers.split(","))
        clips = [c for c in clips if c.driver in keep]
    clips = clips[: args.limit]
    drivers = sorted({c.driver for c in clips})
    if args.split_file:
        split = json.loads(Path(args.split_file).read_text(encoding="utf8"))
    else:
        from build_crops import split_drivers

        split = split_drivers(drivers)
    print(f"{len(clips)} clips, {len(drivers)} drivers", flush=True)
    rows: list[dict] = []
    with ProcessPoolExecutor(args.workers) as ex:
        futs = [ex.submit(label_clip, c, split[c.driver], args.out, args.every_pos,
                          args.every_neg, i) for i, c in enumerate(clips)]
        for i, f in enumerate(as_completed(futs), 1):
            rows += f.result()
            if i % 25 == 0:
                print(f"[boxes] {i}/{len(clips)} clips, {len(rows)} frames", flush=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "meta.csv", "w", newline="", encoding="utf8") as f:
        wr = csv.DictWriter(f, fieldnames=["split", "source", "driver", "label", "image", "boxes"])
        wr.writeheader()
        wr.writerows(rows)
    from collections import Counter

    c = Counter((r["split"], r["label"]) for r in rows)
    for s in ("train", "val", "test"):
        print(s, {k[1]: v for k, v in sorted(c.items()) if k[0] == s})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
