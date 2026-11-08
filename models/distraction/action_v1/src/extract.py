"""Step 2: sampled frames -> upper-body crop (224, gray) + two ear crops (128, gray) + lip gap.

Upper body = square of side 2.5 x face size around the face (shifted down to take in hands at the
ears, chest and cup), clamped to the frame. Ear crops (for the phone-in-hand classifier) are
squares of side 1.2 face widths centred just outside face-mesh landmarks 234 (driver's right ear)
and 454 (left ear). If a frame has no face, the last face <= 1 s old is reused, else the frame is
skipped. Frames within 0.5 s of a segment boundary are dropped.

python extract.py <dataset> [workers]    dataset: syndd | syndd_fish | 3mdad | ebdd | dad
Output: data/crops/<dataset>/... and data/v2/<dataset>.csv
v2 (hybrid): also a lap crop (128, gray) = square of side 2.5 x face size from the chin down,
centred under the face, for the texting phone check (DECISIONS D16). Crops that already exist
are not rewritten, so rows match the v1 CSVs in data/.
"""
import csv
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

A = Path("D:/rtdms-data/action_v1")
DATA = Path("D:/rtdms-data")
OUT = A / "data"
REPO = Path(r"C:\Users\youss\projects\RTDMS\models")
sys.path.insert(0, str(REPO / "distraction" / "src"))
FACE_TASK = REPO / "face" / "models" / "face_landmarker.task"
FPS = 2.5
EDGE = 0.5
HOLD = 1.0
TILES = ((0.0, 0.6), (0.2, 0.8), (0.4, 1.0))
LAP_SIDE, LAP_DOWN = 2.5, 1.25  # lap crop: side and centre below the chin, in face sizes
R_EAR, L_EAR, LIP_T, LIP_B = 234, 454, 13, 14
FIELDS = ["up", "ear_r", "ear_l", "lap", "dataset", "driver", "split", "label", "cls", "side", "clip", "t",
          "lip", "fw", "face"]

SYNDD_MAP = {"normal": "normal", "drinking": "drinking", "phone_right_ear": "call",
             "phone_left_ear": "call", "phone_in_hand": "texting", "eating": "eating",
             "neg_hand_on_head": "hand_on_face", "neg_yawning": "hand_on_face",
             "neg_reaching": "other", "neg_control_panel": "other", "neg_talking": "other",
             "neg_singing": "other"}
MDAD_MAP = {1: "normal", 2: "hand_on_face", 3: "other", 4: "other", 5: "texting", 6: "texting",
            7: "call", 8: "call", 10: "other", 11: "other", 12: "hand_on_face", 13: "drinking",
            14: "drinking", 15: "other", 16: "other"}
MDAD_SIDE = {7: "L", 8: "R"}  # 3MDAD is mirrored: AC7 phone shows at landmark 454 (D11)
EBDD_MAP = {"ATTENTIVE": "normal", "CELL_PHONE": "call", "TEXT": "texting", "EATING": "eating",
            "UNATTENTIVE": "other"}
DAD_MAP = {"talking_with_phone_left": ("call", "L"), "talking_with_phone_right": ("call", "R"),
           "messaging_left": ("texting", ""), "messaging_right": ("texting", ""),
           "drinking": ("drinking", ""), "adjusting_radio": ("other", ""),
           "reaching_behind": ("other", ""), "talking_with_passenger": ("other", "")}


# ----------------------------------------------------------------------------- geometry
def square(img, cx, cy, side):
    """Square crop centred at (cx, cy), shifted (not cut) to stay inside the image."""
    h, w = img.shape[:2]
    side = int(round(min(side, w, h)))
    x1 = int(round(min(max(cx - side / 2, 0), w - side)))
    y1 = int(round(min(max(cy - side / 2, 0), h - side)))
    return img[y1:y1 + side, x1:x1 + side]


def stretch(img):
    """Per-crop contrast stretch (1st-99th percentile -> 0-255); same call at inference. Makes
    dark IR (DAD) and bright RGB-gray crops look alike."""
    lo, hi = np.percentile(img, (1, 99))
    if hi - lo < 8:
        return img
    return np.clip((img.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)


def crops(gray, lm):
    """lm: (478, 2) pixels in `gray` -> (upper 224, ear_r 128, ear_l 128, lap 128, lip gap,
    face width)."""
    x1, y1 = lm.min(0)
    x2, y2 = lm.max(0)
    fh, fwid = y2 - y1, x2 - x1
    size = max(fh, fwid)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    side = 2.5 * size
    up = stretch(cv2.resize(square(gray, cx, cy + 0.3 * size, side), (224, 224),
                            interpolation=cv2.INTER_AREA))
    fw = float(np.linalg.norm(lm[R_EAR] - lm[L_EAR])) or fwid
    ears = []
    for e, other in ((R_EAR, L_EAR), (L_EAR, R_EAR)):
        out = lm[e] - lm[other]
        out = out / (np.linalg.norm(out) or 1.0)
        c = lm[e] + out * 0.25 * fw + np.array([0, 0.1 * fw])
        ears.append(stretch(cv2.resize(square(gray, c[0], c[1], 1.2 * fw), (128, 128),
                                       interpolation=cv2.INTER_AREA)))
    lip = float(np.linalg.norm(lm[LIP_T] - lm[LIP_B]) / fw)
    lap = stretch(cv2.resize(square(gray, cx, y2 + LAP_DOWN * size, LAP_SIDE * size), (128, 128),
                             interpolation=cv2.INTER_AREA))
    return up, ears[0], ears[1], lap, lip, fw


class Faces:
    """MediaPipe Face Landmarker, IMAGE mode, largest face (one per process)."""

    def __init__(self):
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        opts = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(FACE_TASK)),
            running_mode=vision.RunningMode.IMAGE, num_faces=2,
            min_face_detection_confidence=0.4, min_face_presence_confidence=0.4)
        self.lm = vision.FaceLandmarker.create_from_options(opts)

    def _detect(self, gray):
        import mediapipe as mp

        rgb = np.ascontiguousarray(cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB))
        res = self.lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        if not res.face_landmarks:
            return None
        h, w = gray.shape[:2]
        best = None
        for f in res.face_landmarks:
            pts = np.array([(p.x * w, p.y * h) for p in f], np.float64)
            area = np.ptp(pts[:, 0]) * np.ptp(pts[:, 1])
            if best is None or area > best[0]:
                best = (area, pts)
        return best[1]

    def __call__(self, gray, upscale=1.0):
        """Whole frame first; on a miss, three overlapping tiles (60% wide, top 80%), because the
        face detector shrinks the whole frame to 128 px and misses small or turned faces."""
        img = gray if upscale == 1.0 else cv2.resize(gray, None, fx=upscale, fy=upscale,
                                                     interpolation=cv2.INTER_CUBIC)
        lm = self._detect(img)
        if lm is None:
            h, w = img.shape[:2]
            for a, b in TILES:
                x1, x2 = int(a * w), int(b * w)
                lm = self._detect(img[: int(0.8 * h), x1:x2])
                if lm is not None:
                    lm = lm + [x1, 0]
                    break
        return None if lm is None else lm / upscale


_FACES = None


def faces():
    global _FACES
    if _FACES is None:
        _FACES = Faces()
    return _FACES


class Writer:
    def __init__(self, ds, key):
        self.dir = OUT / "crops" / ds / key
        self.dir.mkdir(parents=True, exist_ok=True)
        self.rows = []
        self.ds = ds
        self.miss = 0

    def add(self, gray, lm, idx, held, **meta):
        up, er, el, lap, lip, fw = crops(gray, lm)
        stem = f"{idx:06d}"
        paths = []
        for suf, im in (("up", up), ("er", er), ("el", el), ("lp", lap)):
            p = self.dir / f"{stem}_{suf}.jpg"
            if not p.exists():  # v1 crops stay byte-identical (hard-linked into data/cls)
                cv2.imwrite(str(p), im, [cv2.IMWRITE_JPEG_QUALITY, 90])
            paths.append(str(p.relative_to(OUT)).replace("\\", "/"))
        self.rows.append({"up": paths[0], "ear_r": paths[1], "ear_l": paths[2], "lap": paths[3],
                          "dataset": self.ds,
                          "lip": round(lip, 4), "fw": round(fw, 1), "face": "held" if held else "yes",
                          **meta})


def result(w):
    return {"rows": w.rows, "miss": w.miss}


class Holder:
    """Reuse the last face for up to HOLD seconds."""

    def __init__(self):
        self.lm, self.t = None, -1e9

    def __call__(self, lm, t):
        if lm is not None:
            self.lm, self.t = lm, t
            return lm, False
        if self.lm is not None and t - self.t <= HOLD:
            return self.lm, True
        return None, False


# ----------------------------------------------------------------------------- jobs
def job_syndd(video):
    from rtdms_distraction import datasets as D

    split = json.load(open(REPO / "distraction" / "configs" / "syndd_split.json"))
    segs = [s for s in D.syndd(DATA / "public/syndd/A1") if str(s.video) == video
            and s.label in SYNDD_MAP]
    if not segs:
        return {"rows": [], "miss": 0}
    z = np.load(DATA / "eval_cache/faces/fps10" / f"{Path(video).stem}.npz")
    cache = {round(float(t), 1): (bool(o), lm) for t, o, lm in zip(z["t"], z["ok"], z["lm"],
                                                                    strict=True)}
    cap = cv2.VideoCapture(video)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(src_fps / FPS))
    scale = cap.get(cv2.CAP_PROP_FRAME_WIDTH) / 640.0  # cache is in the 640-wide live view
    w = Writer("syndd", Path(video).stem)
    hold = Holder()
    seg_i = {id(s): k for k, s in enumerate(segs)}
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
        t = i / src_fps
        i += 1
        o, lm = cache.get(round(t, 1), (False, None))
        lm, held = hold(lm * scale if o else None, t)
        seg = next((s for s in segs if s.start_s + EDGE <= t <= s.end_s - EDGE), None)
        if seg is None:
            continue
        if lm is None:
            w.miss += 1
            continue
        side = "R" if seg.label == "phone_right_ear" else "L" if seg.label == "phone_left_ear" else ""
        gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        w.add(gray, lm, i, held, driver=seg.driver, split=split.get(seg.driver, ""),
              label=seg.label, cls=SYNDD_MAP[seg.label], side=side,
              clip=f"{Path(video).stem}_{seg_i[id(seg)]:03d}", t=round(t, 2))
    cap.release()
    return result(w)


def job_mdad(folder):
    sp = json.load(open(A / "splits" / "3mdad.json"))
    d = Path(folder)
    s = int(re.search(r"S(\d+)", d.parent.name).group(1))
    a = int(re.search(r"AC(\d+)", d.name).group(1))
    split = "test" if s in sp["test"] else "train"

    def num(p):
        m = re.search(r"F(\d+)\.", p.name)
        return int(m.group(1)) if m else 0
    imgs = sorted(d.glob("*.jpg"), key=num)
    every = 1 if split == "test" else 2  # test: every stored frame (~3 per s assumed)
    w = Writer("3mdad", f"S{s}_AC{a}")
    hold = Holder()
    for k, p in enumerate(imgs[::every]):
        g = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        t = k * every / 3.0
        lm, held = hold(faces()(g), t)
        if lm is None:
            w.miss += 1
            continue
        w.add(g, lm, k, held, driver=f"3mdad_s{s}", split=split, label=f"AC{a}", cls=MDAD_MAP[a],
              side=MDAD_SIDE.get(a, ""), clip=f"S{s}_AC{a}", t=round(t, 2))
    return result(w)


def job_ebdd(video):
    v = Path(video)
    stem = re.sub(r"\s+", "", v.stem).upper()
    key = next(k for k in EBDD_MAP if stem.endswith("_" + k))
    drv = "ebdd_" + stem[: -len(key) - 1].lower()
    split = "test" if drv in ("ebdd_akkas", "ebdd_jewel") else "train"
    cap = cv2.VideoCapture(video)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, round(src_fps / FPS))
    w = Writer("ebdd", f"{drv}_{key}")
    hold = Holder()
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
        t = i / src_fps
        i += 1
        if t < EDGE or t > n / src_fps - EDGE:
            continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        lm, held = hold(faces()(g), t)
        if lm is None:
            w.miss += 1
            continue
        w.add(g, lm, i, held, driver=drv, split=split, label=key, cls=EBDD_MAP[key], side="",
              clip=f"{drv}_{key}", t=round(t, 2))
    cap.release()
    return result(w)


def job_dad(folder):
    d = Path(folder)  # .../DAD/TesterN/<action>/front_IR
    tester, action = d.parent.parent.name, d.parent.name
    cls, side = ("normal", "") if action.startswith("normal") else DAD_MAP[action]
    idx = sorted(int(re.search(r"img_(\d+)", p.name).group(1)) for p in d.glob("img_*.png"))
    step = round(45 / FPS)
    w = Writer("dad", f"{tester}_{action}")
    hold = Holder()
    first, last = idx[0], idx[-1]
    for i in idx[::step]:
        t = i / 45.0
        if (i - first) / 45 < EDGE or (last - i) / 45 < EDGE:
            continue
        g = cv2.imread(str(d / f"img_{i}.png"), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        lm, held = hold(faces()(g, upscale=2.0), t)
        if lm is None:
            w.miss += 1
            continue
        w.add(g, lm, i, held, driver=f"dad_{tester.lower()}", split="test", label=action, cls=cls,
              side=side, clip=f"{tester}_{action}", t=round(t, 2))
    return result(w)


def job_fish(rows):
    """det_v2/syndd_fish frames (simulated fisheye + driver ROI), train split only."""
    w = Writer("syndd_fish", f"train_{rows[0]['_k']:06d}")
    for k, r in enumerate(rows):
        g = cv2.imread(str(DATA / "det_v2/syndd_fish/images" / r["image"]), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        lm = faces()(g, upscale=1.5)
        if lm is None:
            w.miss += 1
            continue
        side = "R" if r["label"] == "phone_right_ear" else "L" if r["label"] == "phone_left_ear" else ""
        w.add(g, lm, int(r["_k"]), False, driver=r["driver"], split="train", label=r["label"],
              cls=SYNDD_MAP[r["label"]], side=side, clip=Path(r["image"]).stem, t=0.0)
    return result(w)


def jobs(ds):
    if ds == "syndd":
        from rtdms_distraction import datasets as D

        return job_syndd, sorted({str(s.video) for s in D.syndd(DATA / "public/syndd/A1")})
    if ds == "3mdad":
        root = DATA / "raw/3mdad/front/Day-RGB2/RGB2"
        return job_mdad, [str(d) for s in sorted(root.glob("S*")) for d in sorted(s.glob("AC*"))
                          if int(re.search(r"AC(\d+)", d.name).group(1)) in MDAD_MAP]
    if ds == "ebdd":
        return job_ebdd, [str(p) for p in sorted((DATA / "raw/ebdd/x").rglob("*.mp4"))
                          if any(re.sub(r"\s+", "", p.stem).upper().endswith("_" + k)
                                 for k in EBDD_MAP)]
    if ds == "dad":
        return job_dad, [str(p) for p in sorted((DATA / "raw/dad/x/DAD").glob("Tester*/*/front_IR"))]
    if ds == "syndd_fish":
        rows = [r for r in csv.DictReader(open(DATA / "det_v2/syndd_fish/meta_train.csv",
                                               encoding="utf8")) if r["label"] in SYNDD_MAP]
        for k, r in enumerate(rows):
            r["_k"] = k
        return job_fish, [rows[i:i + 300] for i in range(0, len(rows), 300)]
    raise SystemExit(f"unknown dataset {ds}")


def main():
    ds = sys.argv[1]
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    fn, items = jobs(ds)
    print(f"{ds}: {len(items)} jobs", flush=True)
    rows, miss = [], 0
    with ProcessPoolExecutor(workers) as ex:
        for k, r in enumerate(ex.map(fn, items), 1):
            rows += r["rows"]
            miss += r["miss"]
            if k % 10 == 0 or k == len(items):
                print(f"  {k}/{len(items)} jobs, {len(rows)} frames, {miss} skipped (no face)",
                      flush=True)
    (OUT / "v2").mkdir(parents=True, exist_ok=True)
    with open(OUT / "v2" / f"{ds}.csv", "w", newline="", encoding="utf8") as f:
        wr = csv.DictWriter(f, fieldnames=FIELDS)
        wr.writeheader()
        wr.writerows(rows)
    print(f"{ds}: {len(rows)} frames -> {OUT / 'v2' / (ds + '.csv')}", flush=True)


if __name__ == "__main__":
    main()
