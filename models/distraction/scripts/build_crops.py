#!/usr/bin/env python3
"""Build ear-crop (phone / hand_no_phone / none) and mouth-crop (drink / food / none) datasets
from front-facing driver videos, cropped exactly like live.py (same face mesh + crop functions).

    python scripts/build_crops.py --syndd D:/rtdms-data/public/syndd \
        --3mdad D:/rtdms-data/raw/3mdad/front --ebdd D:/rtdms-data/raw/ebdd/x --out crops_v2

Sources (adapters in rtdms_distraction.datasets; front / windshield views only):
  SynDD rear-view (mirror) camera: the main source. Annotated spans of the rear-view videos
    only (dashboard and right-window views are never read). Phone call right / left ->
    phone at that ear (frames assumed NOT mirrored; --syndd-mirrored flips this, check the
    ear-phone sheet), drinking -> drink while CLIP agrees, eating -> food while the wrist is
    at the mouth, hand on head -> hand_no_phone at the ear the wrist is at, texting / yawning
    / singing / talking -> none.
  3MDAD front view, day RGB. A7 / A8 phone (right / left hand) -> phone at that ear, the
    other ear none. RGB2 frames are mirrored (checked on contact sheets: A7 phones sit at
    image right), so the driver's right ear is landmark 454 there. A2 hair/makeup ->
    hand_no_phone at an ear where the pose wrist is. A13/A14 drinking -> mouth drink while
    CLIP zero-shot scores the mouth region as drinking (>= --drink-min; frames in between are
    skipped, not labelled none). A16 smoking -> mouth none (hard negative: hand at the
    mouth, no drink / food). A1, A3-A6, A10, A11 -> none.
  EBDD (windshield camera): talking on the phone -> phone at the ear where the pose wrist is;
    eating -> mouth food while the wrist is at the mouth; cautious / texting / cabin
    equipment -> none.
  Open Images (optional): hand-at-face crops -> ear hand_no_phone; food touching the lips ->
    mouth food (contact-sheet check: ~30/36 someone eating), with as many no-food faces ->
    mouth none so "photo" does not become a shortcut for "food"; a hand over the mouth /
    cheek / chin with no food, drink or phone in the image -> mouth none (live test: hand
    on the cheek gave P(food) 0.99). 3MDAD A2 hair / makeup -> mouth none as well.
  3MDAD gives NO ear crops (NO_EAR: low dashboard angle, phone seen from the side).
Crops whose label depends on the wrist are skipped when the wrist is not where it should be
(the clip label covers the whole action, including reaching for the cup).
Split BY DRIVER within each dataset (70/15/15), so every split has drivers of both.
Output: <root>/crops/{ear,mouth}/{train,val,test}/<class>/*.jpg + manifest.csv
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

from rtdms_distraction import datasets as D  # noqa: E402
from rtdms_distraction.config import load_pipeline_config  # noqa: E402
from rtdms_distraction.ear_clf import crop_ear, crop_mouth, ear_center, mouth_center  # noqa: E402
from rtdms_distraction.facemesh import FaceMesh  # noqa: E402
from rtdms_distraction.pose import PoseEstimator, driver_person  # noqa: E402
from rtdms_distraction.rules import face_scale  # noqa: E402

R_EAR, L_EAR = 234, 454  # driver's right / left ear in a non-mirrored image
MIRRORED = {"3mdad"}  # sources whose frames are mirrored (driver's right ear at image right)
# No ear crops from these: the 3MDAD front view is a low dashboard camera seeing the face at
# 30-45 deg, so the phone is seen from the side; at a mirror-mounted camera it is hidden
# behind the hand (live test 2026-10-11: the 3MDAD-trained ear classifier gave P(phone) 0.00
# from the front).
NO_EAR = {"3mdad"}
# Mouth "none" crops kept first when "none" is capped: a hand at the face with no food.
HARD_NONE = {"hand_at_face", "hair_makeup", "smoking"}
WRISTS = (9, 10)

# action -> (ear rule, mouth rule). Ear rules: "none", "phone_R", "phone_L", "phone_wrist",
# "hand_wrist" (label at the ear the wrist is at; skip otherwise), None = skip ears.
# Mouth rules: "none", "drink_clip" (only while CLIP scores the mouth region as drinking;
# the wrist is often far from the lips when a bottle is tipped up),
# "food_wrist" (only while the wrist is at the mouth), None = skip mouth.
RULES = {
    "normal": ("none", "none"),
    "phone_right_ear": ("phone_R", "none"),
    "phone_left_ear": ("phone_L", "none"),
    "phone_unknown_ear": ("phone_wrist", "none"),
    "phone_in_hand": ("none", "none"),
    "hair_makeup": ("hand_wrist", "none"),
    "drinking": ("none", "drink_clip"),
    "eating": ("none", "food_wrist"),
    "smoking": ("none", "none"),
    "neg_talking": ("none", "none"),
    "neg_singing": ("none", "none"),
    "neg_yawning": ("none", "none"),
    "neg_hand_on_head": ("hand_wrist", "none"),
    "other_none": ("none", "none"),
}
# The rear-passenger guard (driver_face) was tuned on 3MDAD / EBDD frame layouts; SynDD's
# mirror camera puts the driver elsewhere in a 1080p frame, and the cabin has no passenger.
NO_FACE_GUARD = {"syndd"}


class ClipDrinkTeacher:
    """CLIP zero-shot 'drinking' vs 'not' on a square of zoom x the mouth crop. Detectors
    (yolo26m COCO, YOLO-World, zoomed or not) and hand landmarks missed most cups at the lips
    on 3MDAD contact sheets (hand and face hide them); CLIP ViT-L/14 scored nearly every one
    >= 0.97 and smoking crops (hand + cigarette at the mouth) mostly < 0.6."""

    DRINK = ["a person drinking from a cup", "a person drinking from a bottle",
             "a person drinking from a glass", "a cup held against a person's lips"]
    OTHER = ["a close-up photo of a person's mouth and chin", "a person talking",
             "a person touching their face with a hand", "a person smoking a cigarette",
             "a person eating food"]

    def __init__(self, model="ViT-L/14", zoom=1.6, device=None):
        import clip  # ultralytics' CLIP dependency (YOLO-World)
        import torch

        self.torch, self.zoom = torch, zoom
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model, self.prep = clip.load(model, device=self.device)
        with torch.no_grad():
            t = self.model.encode_text(clip.tokenize(self.DRINK + self.OTHER).to(self.device))
            self.text = (t / t.norm(dim=-1, keepdim=True)).float()

    def p_drink(self, frame, center, side, n=224) -> float:
        from PIL import Image

        big = self.zoom * side
        s = n / big
        x0, y0 = center - big / 2
        m = np.array([[s, 0, -x0 * s], [0, s, -y0 * s]])
        roi = cv2.cvtColor(cv2.warpAffine(frame, m, (n, n)), cv2.COLOR_BGR2RGB)
        with self.torch.no_grad():
            im = self.model.encode_image(self.prep(Image.fromarray(roi)).unsqueeze(0)
                                         .to(self.device)).float()
            im = im / im.norm(dim=-1, keepdim=True)
            p = (100 * im @ self.text.T).softmax(-1)[0]
        return float(p[:len(self.DRINK)].sum())


def split_drivers(drivers, seed=1337):
    d = sorted(drivers)
    random.Random(seed).shuffle(d)
    n = len(d)
    n_test = max(1, round(0.15 * n))
    n_val = max(1, round(0.15 * n))
    out = dict.fromkeys(d[:n_test], "test")
    out.update(dict.fromkeys(d[n_test:n_test + n_val], "val"))
    out.update(dict.fromkeys(d[n_test + n_val:], "train"))
    return out


def driver_face(face, w, max_x=0.85, min_fw=0.1) -> bool:
    """3MDAD front view: the tracker sometimes locks onto the rear passenger, a small face at
    the right image edge (s6, s29 on the per-driver sheet). The driver's face is ~90-110 px
    wide in 640 px frames, centred left of 0.85 w."""
    return face.center[0] <= max_x * w and face_scale(face) >= min_fw * w


def in_frame(center, side, w, h) -> float:
    """Fraction of the crop square inside the image (the rest is black padding)."""
    x0, y0 = center - side / 2
    iw = max(0.0, min(w, x0 + side) - max(0.0, x0))
    ih = max(0.0, min(h, y0 + side) - max(0.0, y0))
    return iw * ih / (side * side)


def wrist_near(person, point, fw, max_fw=0.9) -> bool:
    """0.9 fw: on 3MDAD hair / makeup sheets the hand is in the ear crop up to ~0.9 fw."""
    if person is None:
        return False
    return any(person.kpts[w, 2] >= 0.3 and np.linalg.norm(person.kpts[w, :2] - point) <=
               max_fw * fw for w in WRISTS)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--syndd", help="SynDD folder (per-driver CSVs + rear-view videos)")
    p.add_argument("--syndd-mirrored", action="store_true",
                   help="SynDD rear-view frames are mirrored (driver's right ear at image right)")
    p.add_argument("--3mdad", dest="mdad", help="3MDAD front-view (day RGB) folder")
    p.add_argument("--ebdd", help="extracted EBDD folder")
    p.add_argument("--out", default="crops",
                   help="output folder under the data root (a new name keeps older crops)")
    p.add_argument("--no-openimages", action="store_true")
    p.add_argument("--every", type=float, default=0.33, help="seconds between sampled frames")
    p.add_argument("--max-none-ratio", type=float, default=2.0)
    p.add_argument("--store-size", type=int, help="crop side in px (default: config imgsz)")
    p.add_argument("--min-in", type=float, default=0.75,
                   help="min fraction of a crop inside the frame")
    p.add_argument("--drink-min", type=float, default=0.97, help="CLIP P(drinking) for drink")
    p.add_argument("--limit-clips", type=int, help="clips per dataset (smoke test)")
    args = p.parse_args()

    pcfg = load_pipeline_config(profile="laptop_webcam")
    ec, mc = pcfg.ear_classifier, pcfg.mouth_classifier
    if args.store_size:  # store larger crops; training / eval downscale (size study)
        ec.imgsz = mc.imgsz = args.store_size
    dcfg = yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))
    out = Path(dcfg["root"]) / args.out
    pose = PoseEstimator(pcfg.pose)
    rows: list[dict] = []
    mirrored = MIRRORED | ({"syndd"} if args.syndd_mirrored else set())

    clips: list[D.Clip] = []
    if args.syndd:
        clips += D.syndd_clips(args.syndd)[: args.limit_clips]
    if args.mdad:
        clips += D.mdad3_front(args.mdad)[: args.limit_clips]
    if args.ebdd:
        clips += D.ebdd(args.ebdd)[: args.limit_clips]
    if not clips and args.no_openimages:
        raise SystemExit("nothing to do: pass --syndd, --3mdad and/or --ebdd")
    teacher = ClipDrinkTeacher() if any(
        RULES.get(c.label, (None, None))[1] == "drink_clip" for c in clips) else None
    splits = {}
    for src in {c.source for c in clips}:
        splits.update(split_drivers({c.driver for c in clips if c.source == src}))

    def save(kind, crop, label, split, clip, name):
        d = out / kind / split / label
        d.mkdir(parents=True, exist_ok=True)
        fn = f"{clip.source}__{clip.driver}__{name}.jpg"
        cv2.imwrite(str(d / fn), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        rows.append({"kind": kind, "file": f"{split}/{label}/{fn}", "split": split,
                     "label": label, "source": clip.source, "driver": clip.driver,
                     "action": clip.label})

    for ci, clip in enumerate(clips, 1):
        ear_rule, mouth_rule = RULES.get(clip.label, (None, None))
        if clip.source in NO_EAR:
            ear_rule = None
        if ear_rule is None and mouth_rule is None:
            continue
        split = splits[clip.driver]
        mesh = None
        next_t, k = 0.0, 0
        held, held_t = None, -1e9
        # The mesh sees every frame (its face search and tracker assume live frame rate);
        # crops are saved every args.every seconds. A hidden face (cup, phone) is held for
        # face_hold_s, as live.py does.
        for t, frame in clip.frames(0.0):
            if mesh is None:  # one tracker per clip, sized to the clip, like live.py
                h, w = frame.shape[:2]
                mesh = FaceMesh(pcfg.facemesh, w, h, np.array([[w, 0, w / 2], [0, w, h / 2],
                                                              [0, 0, 1.0]]))
            face = mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), t)
            if face is not None and clip.source not in NO_FACE_GUARD and \
                    not driver_face(face, w):
                face = None  # a passenger: drop it and make the cropper search again
                mesh.cropper.tracking = False
            if face is not None:
                held, held_t = face, t
            elif held is not None and t - held_t <= mc.face_hold_s:
                face = held
            if face is None or t < next_t:
                continue
            next_t, k = t + args.every, k + 1
            lm, fw = face.landmarks, face_scale(face)
            needs_pose = (ear_rule in ("phone_wrist", "hand_wrist") or
                          mouth_rule == "food_wrist")
            person = driver_person(pose.detect(frame), face.center) if needs_pose else None
            name = f"{Path(clip.name).stem}_{k:05d}"
            # ---- ears
            ear_labels = {}
            if ear_rule == "none":
                ear_labels = {R_EAR: "none", L_EAR: "none"}
            elif ear_rule in ("phone_R", "phone_L"):
                right = ear_rule == "phone_R"
                if clip.source in mirrored:
                    right = not right
                phone_ear = R_EAR if right else L_EAR
                ear_labels = {R_EAR: "none", L_EAR: "none", phone_ear: "phone"}
            elif ear_rule in ("phone_wrist", "hand_wrist"):
                lab = "phone" if ear_rule == "phone_wrist" else "hand_no_phone"
                at = [e for e in (R_EAR, L_EAR)
                      if wrist_near(person, ear_center(lm, e, ec.outward, fw), fw)]
                if len(at) == 1:
                    ear_labels = {at[0]: lab}
                    if lab == "phone":
                        ear_labels[L_EAR if at[0] == R_EAR else R_EAR] = "none"
            for e, lab in ear_labels.items():
                if in_frame(ear_center(lm, e, ec.outward, fw), ec.scale * fw, w, h) < args.min_in:
                    continue
                crop = crop_ear(frame, lm, e, ec.imgsz, ec.scale, ec.outward, fw, ec.grayscale)
                save("ear", crop, lab, split, clip, f"{name}_{'R' if e == R_EAR else 'L'}")
            # ---- mouth
            mlab = None
            if mouth_rule == "none":
                mlab = "none"
            elif mouth_rule == "drink_clip":
                pd = teacher.p_drink(frame, mouth_center(lm, mc.down, fw), mc.scale * fw)
                if pd >= args.drink_min:
                    mlab = "drink"
            elif mouth_rule == "food_wrist" and \
                    wrist_near(person, mouth_center(lm, mc.down, fw), fw):
                mlab = "food"
            if mlab and in_frame(mouth_center(lm, mc.down, fw), mc.scale * fw, w, h) >= \
                    args.min_in:
                crop = crop_mouth(frame, lm, mc.imgsz, mc.scale, mc.down, fw, mc.grayscale)
                save("mouth", crop, mlab, split, clip, name)
        if mesh is not None:
            mesh.close()
        if ci % 20 == 0:
            print(f"[crops] {ci}/{len(clips)} clips, {len(rows)} crops", flush=True)

    if not args.no_openimages:
        rows += openimages_hand_crops(dcfg, ec, out)
        rows += openimages_mouth_crops(dcfg, mc, out)
        rows += openimages_hand_face_crops(dcfg, mc, out)

    # balance 'none' per kind and split, then write manifests
    rng = random.Random(7)
    for kind in ("ear", "mouth"):
        for split in ("train", "val", "test"):
            sel = [r for r in rows if r["kind"] == kind and r["split"] == split]
            others = Counter(r["label"] for r in sel if r["label"] != "none")
            cap = int(args.max_none_ratio * max(others.values(), default=1))
            nones = [r for r in sel if r["label"] == "none"]
            rng.shuffle(nones)
            nones.sort(key=lambda r: r["action"] not in HARD_NONE)  # hard negatives first
            for r in nones[cap:]:
                (out / kind / r["file"]).unlink(missing_ok=True)
                r["dropped"] = True
    rows = [r for r in rows if not r.get("dropped")]
    for kind in ("ear", "mouth"):
        kr = [r for r in rows if r["kind"] == kind]
        if not kr:
            continue
        with open(out / kind / "manifest.csv", "w", newline="", encoding="utf8") as f:
            w = csv.DictWriter(f, fieldnames=list(kr[0].keys()))
            w.writeheader()
            w.writerows(kr)
        c = Counter((r["split"], r["label"]) for r in kr)
        labels = sorted({r["label"] for r in kr})
        print(f"\n{kind} crops")
        for split in ("train", "val", "test"):
            drivers = len({r["driver"] for r in kr if r["split"] == split})
            print(f"  {split:5s} ({drivers:3d} drivers) " +
                  "  ".join(f"{lab} {c[(split, lab)]}" for lab in labels))
        print("  by source:", dict(Counter((r["source"], r["label"]) for r in kr)))
    print(f"-> {out}")
    return 0


def lip_dist(b, w, h, mx, my) -> tuple[float, float]:
    """Pixel distance from the mouth centre to a normalised YOLO box, and the box width."""
    x1, y1 = (b[1] - b[3] / 2) * w, (b[2] - b[4] / 2) * h
    x2, y2 = (b[1] + b[3] / 2) * w, (b[2] + b[4] / 2) * h
    return float(np.hypot(max(x1 - mx, 0, mx - x2), max(y1 - my, 0, my - y2))), x2 - x1


def openimages_mouth_crops(dcfg, mc, out) -> list[dict]:
    """Open Images (ground-truth boxes only, its own splits): a food box touching the lips
    (within 0.15 fw of the mouth centre, narrower than 3 fw) -> mouth food. A contact-sheet
    check on 36 random crops: ~30 show someone eating (misfits: a juice box, a gift box,
    bubble gum). To keep 'photo' from becoming a shortcut for 'food', the same number of
    Open Images faces with no food / drink within 1 fw of the mouth -> mouth none."""
    import mediapipe as mp
    from mediapipe.tasks import python as mpp
    from mediapipe.tasks.python import vision

    from rtdms_distraction.types import FaceObservation

    pcfg = load_pipeline_config(profile="laptop_webcam")
    lmk = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=mpp.BaseOptions(model_asset_path=str((ROOT / pcfg.facemesh.model_path)
                                                          .resolve())),
        running_mode=vision.RunningMode.IMAGE, num_faces=1))
    oi = Path(dcfg["root"]) / "openimages"
    rows, n_food = [], Counter()

    def write(split, label, stem, crop):
        d = out / "mouth" / split / label
        d.mkdir(parents=True, exist_ok=True)
        fn = f"openimages__{stem}.jpg"
        cv2.imwrite(str(d / fn), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        rows.append({"kind": "mouth", "file": f"{split}/{label}/{fn}", "split": split,
                     "label": label, "source": "openimages", "driver": stem,
                     "action": "photo"})

    for split in ("train", "val", "test"):
        faces = json.loads((oi / "meta" / f"{split}_faces.json").read_text(encoding="utf8"))
        n_none = 0
        for lab_p in sorted((oi / "labels_gt" / split).glob("*.txt")):
            if not faces.get(lab_p.stem):
                continue
            boxes = [(int(r[0]), *map(float, r[1:])) for r in
                     (ln.split() for ln in lab_p.read_text(encoding="utf8").split("\n")
                      if ln.strip())]
            has_food = any(b[0] == 2 for b in boxes)
            if not has_food and n_none >= n_food[split]:
                continue  # 'none' only as many as 'food' so far
            img = cv2.imread(str(oi / "images" / split / f"{lab_p.stem}.jpg"))
            if img is None:
                continue
            res = lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                      data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
            if not res.face_landmarks:
                continue
            h, w = img.shape[:2]
            lm = np.array([(q.x * w, q.y * h) for q in res.face_landmarks[0]])
            fw = face_scale(FaceObservation(lm, None, None, None, "none", None, "geometric", 0))
            mx, my = lm[[13, 14, 61, 291]].mean(0)

            near = [(b[0], *lip_dist(b, w, h, mx, my)) for b in boxes if b[0] in (1, 2)]
            crop = crop_mouth(img, lm, mc.imgsz, mc.scale, mc.down, fw, mc.grayscale)
            if any(c == 2 and d <= 0.15 * fw and bw < 3 * fw for c, d, bw in near):
                write(split, "food", lab_p.stem, crop)
                n_food[split] += 1
            elif all(d > 1.0 * fw for _, d, _ in near) and n_none < n_food[split]:
                write(split, "none", lab_p.stem, crop)
                n_none += 1
    lmk.close()
    print(f"[openimages] mouth food {dict(n_food)}, plus as many 'none' faces")
    return rows


def openimages_hand_face_crops(dcfg, mc, out) -> list[dict]:
    """Open Images: a GT hand box over the mouth crop window (>= 15 % of it: hand on the
    mouth, cheek or chin) in an image with no phone, drink or food box -> mouth none
    (action hand_at_face, kept first when 'none' is capped)."""
    import mediapipe as mp
    from mediapipe.tasks import python as mpp
    from mediapipe.tasks.python import vision

    from rtdms_distraction.types import FaceObservation

    pcfg = load_pipeline_config(profile="laptop_webcam")
    lmk = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=mpp.BaseOptions(model_asset_path=str((ROOT / pcfg.facemesh.model_path)
                                                          .resolve())),
        running_mode=vision.RunningMode.IMAGE, num_faces=1))
    oi = Path(dcfg["root"]) / "openimages"
    rows, n = [], Counter()
    for split in ("train", "val", "test"):
        faces = json.loads((oi / "meta" / f"{split}_faces.json").read_text(encoding="utf8"))
        for lab_p in sorted((oi / "labels_gt" / split).glob("*.txt")):
            if not faces.get(lab_p.stem):
                continue
            boxes = [(int(r[0]), *map(float, r[1:])) for r in
                     (ln.split() for ln in lab_p.read_text(encoding="utf8").split("\n")
                      if ln.strip())]
            if any(b[0] in (0, 1, 2) for b in boxes) or not any(b[0] == 3 for b in boxes):
                continue
            img = cv2.imread(str(oi / "images" / split / f"{lab_p.stem}.jpg"))
            if img is None:
                continue
            res = lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                      data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
            if not res.face_landmarks:
                continue
            h, w = img.shape[:2]
            lm = np.array([(q.x * w, q.y * h) for q in res.face_landmarks[0]])
            fw = face_scale(FaceObservation(lm, None, None, None, "none", None, "geometric", 0))
            cx, cy = mouth_center(lm, mc.down, fw)
            half = mc.scale * fw / 2
            best = 0.0
            for _, bx, by, bw, bh in (b for b in boxes if b[0] == 3):
                x1, y1, x2, y2 = (bx - bw / 2) * w, (by - bh / 2) * h, \
                    (bx + bw / 2) * w, (by + bh / 2) * h
                iw = min(x2, cx + half) - max(x1, cx - half)
                ih = min(y2, cy + half) - max(y1, cy - half)
                if iw > 0 and ih > 0:
                    best = max(best, iw * ih / (4 * half * half))
            if best < 0.15:
                continue
            crop = crop_mouth(img, lm, mc.imgsz, mc.scale, mc.down, fw, mc.grayscale)
            d = out / "mouth" / split / "none"
            d.mkdir(parents=True, exist_ok=True)
            fn = f"openimages__{lab_p.stem}__handface.jpg"
            cv2.imwrite(str(d / fn), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
            rows.append({"kind": "mouth", "file": f"{split}/none/{fn}", "split": split,
                         "label": "none", "source": "openimages", "driver": lab_p.stem,
                         "action": "hand_at_face"})
            n[split] += 1
    lmk.close()
    print(f"[openimages] mouth none, hand at the face: {dict(n)}")
    return rows


def openimages_hand_crops(dcfg, ec, out) -> list[dict]:
    """Open Images: an ear whose crop window holds >= 40 % of a GT hand box, in an image with
    no phone -> ear hand_no_phone (IMAGE-mode face mesh: the photos are unrelated)."""
    import mediapipe as mp
    from mediapipe.tasks import python as mpp
    from mediapipe.tasks.python import vision

    pcfg = load_pipeline_config(profile="laptop_webcam")
    lmk = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=mpp.BaseOptions(model_asset_path=str((ROOT / pcfg.facemesh.model_path)
                                                          .resolve())),
        running_mode=vision.RunningMode.IMAGE, num_faces=1))
    oi = Path(dcfg["root"]) / "openimages"
    rows = []
    for split in ("train", "val", "test"):
        faces = json.loads((oi / "meta" / f"{split}_faces.json").read_text(encoding="utf8"))
        for lab_p in sorted((oi / "labels" / split).glob("*.txt")):
            if not faces.get(lab_p.stem):
                continue
            boxes = [(int(r[0]), *map(float, r[1:])) for r in
                     (ln.split() for ln in lab_p.read_text(encoding="utf8").split("\n")
                      if ln.strip())]
            if any(b[0] == 0 for b in boxes) or not any(b[0] == 3 for b in boxes):
                continue
            img = cv2.imread(str(oi / "images" / split / f"{lab_p.stem}.jpg"))
            if img is None:
                continue
            res = lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                      data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
            if not res.face_landmarks:
                continue
            h, w = img.shape[:2]
            lm = np.array([(q.x * w, q.y * h) for q in res.face_landmarks[0]])
            from rtdms_distraction.types import FaceObservation
            fw = face_scale(FaceObservation(lm, None, None, None, "none", None, "geometric", 0))
            for e in (R_EAR, L_EAR):
                cx, cy = ear_center(lm, e, ec.outward, fw)
                half = ec.scale * fw / 2
                win = (cx - half, cy - half, cx + half, cy + half)
                best = 0.0
                for _, bx, by, bw, bh in (b for b in boxes if b[0] == 3):
                    x1, y1, x2, y2 = (bx - bw / 2) * w, (by - bh / 2) * h, \
                        (bx + bw / 2) * w, (by + bh / 2) * h
                    iw = min(x2, win[2]) - max(x1, win[0])
                    ih = min(y2, win[3]) - max(y1, win[1])
                    if iw > 0 and ih > 0:
                        best = max(best, iw * ih / ((x2 - x1) * (y2 - y1)))
                if best >= 0.4:
                    crop = crop_ear(img, lm, e, ec.imgsz, ec.scale, ec.outward, fw, ec.grayscale)
                    d = out / "ear" / split / "hand_no_phone"
                    d.mkdir(parents=True, exist_ok=True)
                    fn = f"openimages__{lab_p.stem}__{'R' if e == R_EAR else 'L'}.jpg"
                    cv2.imwrite(str(d / fn), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    rows.append({"kind": "ear", "file": f"{split}/hand_no_phone/{fn}",
                                 "split": split, "label": "hand_no_phone",
                                 "source": "openimages", "driver": lab_p.stem,
                                 "action": "hand_at_face"})
    lmk.close()
    print(f"[openimages] {len(rows)} hand_no_phone ear crops")
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
