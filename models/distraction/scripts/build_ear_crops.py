#!/usr/bin/env python3
"""Build the ear-crop classifier dataset: phone / hand_no_phone / none, 128 px crops beside the
ear landmarks (234 = driver's right, 454 = driver's left), colour by default.

    python scripts/build_ear_crops.py --statefarm data/public/statefarm
    python scripts/build_ear_crops.py --statefarm data/public/statefarm --no-openimages

Sources and labels:
  State Farm (camera beside the driver; split BY DRIVER with driver_imgs_list.csv, 70/15/15)
    c2 "talking on the phone - right": right-ear crop = phone, left-ear crop = none
    c4 "talking on the phone - left":  left-ear crop = phone, right-ear crop = none
    c0 safe driving, c9 talking to passenger: both ears = none
    c8 hair and makeup: an ear where a pose wrist is within 0.6 face widths = hand_no_phone
       (other c8 crops are ambiguous and skipped)
  Open Images (already downloaded; its own splits): an ear whose crop window holds >= 40 % of a
    hand box, in an image with no phone = hand_no_phone (phone labels come from State Farm only).
Crops come from rtdms_distraction.ear_clf.crop_ear, the same function the runtime uses.
Output: <root>/ear_crops/{train,val,test}/{phone,hand_no_phone,none}/*.jpg + manifest.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rtdms_distraction.config import load_pipeline_config  # noqa: E402
from rtdms_distraction.ear_clf import crop_ear  # noqa: E402
from rtdms_distraction.rules import face_scale  # noqa: E402
from rtdms_distraction.types import FaceObservation  # noqa: E402

R_EAR, L_EAR = 234, 454
SF_LABELS = {"c2": {R_EAR: "phone", L_EAR: "none"}, "c4": {L_EAR: "phone", R_EAR: "none"},
             "c0": {R_EAR: "none", L_EAR: "none"}, "c9": {R_EAR: "none", L_EAR: "none"},
             "c8": "pose"}


class Mesh:
    """MediaPipe Face Landmarker in IMAGE mode (independent photos: no tracking)."""

    def __init__(self, model_path: str):
        from mediapipe.tasks import python as mpp
        from mediapipe.tasks.python import vision

        self._lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.IMAGE, num_faces=1))

    def __call__(self, bgr: np.ndarray) -> np.ndarray | None:
        import mediapipe as mp

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        r = self._lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        if not r.face_landmarks:
            return None
        h, w = bgr.shape[:2]
        return np.array([(p.x * w, p.y * h) for p in r.face_landmarks[0]], np.float64)


def fw_of(lm: np.ndarray) -> float:
    return face_scale(FaceObservation(lm, None, None, None, "none", None, "geometric", 0.0))


def ear_window(lm: np.ndarray, ear: int, scale: float, outward: float, fw: float):
    """The crop_ear window in image pixels: (x1, y1, x2, y2)."""
    p = lm[ear]
    u = p - 0.5 * (lm[R_EAR] + lm[L_EAR])
    n = float(np.linalg.norm(u))
    u = u / n if n > 1e-6 else np.array([1.0 if ear == L_EAR else -1.0, 0.0])
    cx, cy = p + outward * fw * u
    half = max(8.0, scale * fw) / 2
    return cx - half, cy - half, cx + half, cy + half


def frac_inside(box, win, w: int, h: int) -> float:
    """Share of a normalised YOLO box (cls, cx, cy, bw, bh) inside a pixel window."""
    _, cx, cy, bw, bh = box
    x1, y1, x2, y2 = (cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h
    iw = min(x2, win[2]) - max(x1, win[0])
    ih = min(y2, win[3]) - max(y1, win[1])
    area = (x2 - x1) * (y2 - y1)
    return iw * ih / area if iw > 0 and ih > 0 and area > 0 else 0.0


def split_drivers(drivers: list[str], seed: int = 1337) -> dict[str, str]:
    d = sorted(drivers)
    random.Random(seed).shuffle(d)
    n = len(d)
    n_test, n_val = max(1, round(0.15 * n)), max(1, round(0.15 * n))
    out = {x: "test" for x in d[:n_test]}
    out.update({x: "val" for x in d[n_test:n_test + n_val]})
    out.update({x: "train" for x in d[n_test + n_val:]})
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--statefarm", help="folder containing driver_imgs_list.csv and imgs/train")
    p.add_argument("--no-openimages", action="store_true")
    p.add_argument("--max-none-ratio", type=float, default=2.0,
                   help="cap 'none' crops at this multiple of 'phone' crops per split")
    p.add_argument("--limit", type=int, help="images per source (smoke test)")
    args = p.parse_args()

    pcfg = load_pipeline_config(profile="laptop_webcam")
    c = pcfg.ear_classifier
    dcfg = yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))
    out = Path(dcfg["root"]) / "ear_crops"
    mesh = Mesh(str((ROOT / pcfg.facemesh.model_path).resolve()))
    rows: list[dict] = []

    def save(img, lm, ear, label, split, source, driver, name):
        crop = crop_ear(img, lm, ear, c.imgsz, c.scale, c.outward, fw_of(lm), c.grayscale)
        d = out / split / label
        d.mkdir(parents=True, exist_ok=True)
        fn = f"{source}__{driver}__{name}__{'R' if ear == R_EAR else 'L'}.jpg"
        cv2.imwrite(str(d / fn), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        rows.append({"file": f"{split}/{label}/{fn}", "split": split, "label": label,
                     "source": source, "driver": driver, "ear": ear})

    # ---- State Farm
    if args.statefarm:
        sf = Path(args.statefarm)
        lst = next(sf.rglob("driver_imgs_list.csv"), None)
        if lst is None:
            raise SystemExit(f"driver_imgs_list.csv not found under {sf}")
        train_dir = next((d for d in sf.rglob("train") if (d / "c0").is_dir()), None)
        if train_dir is None:
            raise SystemExit(f"imgs/train/c0..c9 not found under {sf}")
        items = [r for r in csv.DictReader(open(lst, encoding="utf8"))
                 if r["classname"] in SF_LABELS][: args.limit]
        splits = split_drivers(list({r["subject"] for r in items}))
        pose = None
        if any(r["classname"] == "c8" for r in items):
            from rtdms_distraction.pose import PoseEstimator, driver_person
            pose = PoseEstimator(pcfg.pose)
        n_noface = 0
        for k, r in enumerate(items, 1):
            img = cv2.imread(str(train_dir / r["classname"] / r["img"]))
            if img is None:
                continue
            lm = mesh(img)
            if lm is None:
                n_noface += 1
                continue
            split = splits[r["subject"]]
            lab = SF_LABELS[r["classname"]]
            if lab == "pose":
                person = driver_person(pose.detect(img), 0.5 * (lm[R_EAR] + lm[L_EAR]))
                if person is None:
                    continue
                fw = fw_of(lm)
                for ear in (R_EAR, L_EAR):
                    near = any(person.kpts[w, 2] >= 0.3 and
                               np.linalg.norm(person.kpts[w, :2] - lm[ear]) <= 0.6 * fw
                               for w in (9, 10))
                    if near:
                        save(img, lm, ear, "hand_no_phone", split, "statefarm", r["subject"],
                             Path(r["img"]).stem)
            else:
                for ear, label in lab.items():
                    save(img, lm, ear, label, split, "statefarm", r["subject"],
                         Path(r["img"]).stem)
            if k % 2000 == 0:
                print(f"[statefarm] {k}/{len(items)}", flush=True)
        print(f"[statefarm] {len(items)} images, {n_noface} without a face mesh; "
              f"drivers per split: {Counter(splits.values())}")

    # ---- Open Images: hand at the ear, no phone anywhere in the image -> hand_no_phone
    # A box counts for an ear only if >= 40 % of it lies inside that ear's crop window (the
    # same window the classifier sees). A looser "box beside the face" rule labelled cigarettes,
    # cameras and food as phones on a contact-sheet check.
    if not args.no_openimages:
        oi = Path(dcfg["root"]) / "openimages"
        n_imgs = 0
        for split in ("train", "val", "test"):
            faces = json.loads((oi / "meta" / f"{split}_faces.json").read_text(encoding="utf8"))
            for lab_p in sorted((oi / "labels" / split).glob("*.txt")):
                if not faces.get(lab_p.stem):
                    continue
                rows_l = [ln.split() for ln in lab_p.read_text(encoding="utf8").split("\n")
                          if ln.strip()]
                boxes = [(int(r[0]), *map(float, r[1:])) for r in rows_l]
                if not any(b[0] in (0, 3) for b in boxes):
                    continue
                img = cv2.imread(str(oi / "images" / split / f"{lab_p.stem}.jpg"))
                lm = mesh(img) if img is not None else None
                if lm is None:
                    continue
                h, w = img.shape[:2]
                fw = fw_of(lm)
                has_phone = any(b[0] == 0 for b in boxes)
                saved = False
                for ear in (R_EAR, L_EAR):
                    win = ear_window(lm, ear, c.scale, c.outward, fw)
                    inside = {cls: max((frac_inside(b, win, w, h) for b in boxes if b[0] == cls),
                                       default=0.0) for cls in (0, 3)}
                    # Open Images supplies hand_no_phone only: its "phone at the face" crops were
                    # about half selfies / phones held up in front of the face (contact sheet).
                    if not has_phone and inside[3] >= 0.4:
                        save(img, lm, ear, "hand_no_phone", split, "openimages", lab_p.stem,
                             lab_p.stem)
                        saved = True
                n_imgs += saved
                if args.limit and n_imgs >= args.limit:
                    break
        print(f"[openimages] crops from {n_imgs} images")

    # ---- balance 'none' and write the manifest
    rng = random.Random(7)
    for split in ("train", "val", "test"):
        n_phone = sum(1 for r in rows if r["split"] == split and r["label"] == "phone")
        nones = [r for r in rows if r["split"] == split and r["label"] == "none"]
        cap = int(args.max_none_ratio * max(1, n_phone))
        rng.shuffle(nones)
        for r in nones[cap:]:
            (out / r["file"]).unlink(missing_ok=True)
            r["dropped"] = True
    rows = [r for r in rows if not r.get("dropped")]
    with open(out / "manifest.csv", "w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "split", "label", "source", "driver", "ear"])
        w.writeheader()
        w.writerows(rows)
    counts = Counter((r["split"], r["label"]) for r in rows)
    for split in ("train", "val", "test"):
        print(f"{split:5s} " + "  ".join(f"{lab} {counts[(split, lab)]}"
                                         for lab in ("phone", "hand_no_phone", "none")))
    by_src = Counter((r["source"], r["label"]) for r in rows)
    print("by source:", dict(by_src))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
