"""Adapters for public driver datasets (local paths only; nothing is downloaded).

Each adapter turns a dataset folder into a list of `Segment`s (a labelled time span of one video)
or `Still`s (a labelled image), with a driver id so splits can be made per person.

Behaviour labels (shared with the rule engine):
    normal, phone_right_ear, phone_left_ear, phone_in_hand, drinking, eating
Eval-only hard negatives (never trained as a class, used for false-alarm tests):
    neg_talking, neg_singing, neg_yawning, neg_hand_on_head
Everything else -> None (skipped).

The folder and annotation conventions below are from the datasets' public documentation and
have NOT been checked against the actual downloads yet. Each adapter fails loudly on a layout it
does not recognise; check its summary against the dataset's own README before trusting a split.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXT = (".mp4", ".avi", ".mov", ".mkv", ".m4v")


@dataclass(frozen=True)
class Segment:
    source: str
    driver: str
    video: Path
    start_s: float
    end_s: float
    label: str
    view: str = ""


@dataclass(frozen=True)
class Still:
    source: str
    driver: str
    image: Path
    label: str
    view: str = ""


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def hms(s: str) -> float:
    """'0:01:23' / '01:23' / '83' / '83.5' -> seconds."""
    parts = [float(p) for p in str(s).strip().split(":")]
    out = 0.0
    for p in parts:
        out = out * 60 + p
    return out


# --------------------------------------------------------------------------- SynDD 1/2

SYNDD_LABELS = {
    "normalforwarddriving": "normal",
    "drinking": "drinking",
    "phonecallright": "phone_right_ear",
    "phonecallleft": "phone_left_ear",
    "textright": "phone_in_hand",
    "textleft": "phone_in_hand",
    "eating": "eating",
    # hard negatives for false-alarm tests (spec: "others -> ignore" for TRAINING)
    "handonhead": "neg_hand_on_head",
    "yawning": "neg_yawning",
    "singingwithmusic": "neg_singing",
    "singingordancewithmusic": "neg_singing",
    "singingordancingwithmusic": "neg_singing",
    "talktopassengerattheright": "neg_talking",
    "talktopassengeratbackseat": "neg_talking",
}
REAR_VIEW = {"rearview", "rear", "rearviewmirror"}


def syndd(root: str | Path, view: str = "rear") -> list[Segment]:
    """SynDD1 / SynDD2 (AI City Challenge track 3). Per driver folder: videos for Dashboard,
    Rear_view and Right_side_window, plus a CSV with Filename, Camera View, Activity Type,
    Start Time, End Time. Filename is often only on the first row of a block (forward-filled).
    If the CSV has no rear-view rows, the dashboard rows' times are applied to the rear-view
    video with the same block number (the three views are synchronised)."""
    root = Path(root)
    csvs = sorted(root.rglob("*.csv"))
    if not csvs:
        raise FileNotFoundError(f"SynDD: no annotation CSVs under {root}")
    out: list[Segment] = []
    for c in csvs:
        folder = c.parent
        driver = re.search(r"(\d{4,6})", c.stem)
        driver = f"syndd_{driver.group(1)}" if driver else f"syndd_{norm(c.stem)}"
        videos = {norm(v.stem): v for v in folder.rglob("*") if v.suffix.lower() in VIDEO_EXT}
        rows = list(csv.DictReader(open(c, encoding="utf-8-sig", newline="")))
        if not rows:
            continue
        keys = {norm(k): k for k in rows[0]}
        k_file = keys.get("filename")
        k_view = keys.get("cameraview")
        k_act = keys.get("activitytype")
        k_start, k_end = keys.get("starttime"), keys.get("endtime")
        if not (k_file and k_act and k_start and k_end):
            raise KeyError(f"SynDD: unexpected columns in {c}: {list(rows[0])}")
        last_file = last_view = ""
        has_rear = any(norm(r.get(k_view, "")) in REAR_VIEW for r in rows if k_view)
        for r in rows:
            last_file = r[k_file].strip() or last_file
            last_view = (r.get(k_view) or "").strip() or last_view
            label = SYNDD_LABELS.get(norm(r[k_act]))
            if label is None or not r[k_start].strip():
                continue
            is_rear = norm(last_view) in REAR_VIEW
            if view == "rear":
                if has_rear and not is_rear:
                    continue
                stem = norm(last_file)
                if not has_rear:  # map a dashboard filename to its rear-view sibling
                    stem = re.sub(r"^dashboard", "rearview", stem)
                video = videos.get(stem) or next(
                    (v for k, v in videos.items() if k.startswith(stem)), None)
            else:
                video = videos.get(norm(last_file))
            if video is None:
                continue
            out.append(Segment("syndd", driver, video, hms(r[k_start]), hms(r[k_end]), label,
                               "rear"))
    return out


# --------------------------------------------------------------------------- DMD

DMD_LABELS = {
    "safedrive": "normal",
    "textingright": "phone_in_hand",
    "textingleft": "phone_in_hand",
    "phonecallright": "phone_right_ear",
    "phonecallleft": "phone_left_ear",
    "drinking": "drinking",
    "talkingtopassenger": "neg_talking",
    "hairandmakeup": None,
}


def dmd(root: str | Path, stream: str = "ir_body") -> list[Segment]:
    """DMD distraction set: OpenLABEL / VCD JSON `*_ann_distraction.json` next to the stream
    videos (`*_rgb_body.mp4`, `*_ir_body.mp4`, ...). Actions are `driver_actions/<name>` with
    frame intervals. Frame numbers are converted with the stream's own fps."""
    import cv2

    root = Path(root)
    anns = sorted(root.rglob("*ann_distraction.json"))
    if not anns:
        raise FileNotFoundError(f"DMD: no *_ann_distraction.json under {root}")
    out: list[Segment] = []
    for a in anns:
        doc = json.loads(a.read_text(encoding="utf8"))
        body = doc.get("openlabel") or doc.get("vcd")
        if body is None:
            raise KeyError(f"DMD: {a} is neither OpenLABEL nor VCD")
        prefix = a.name.split("_rgb_ann")[0].split("_ann")[0]
        video = next(iter(sorted(a.parent.glob(f"{prefix}*_{stream}.*"))), None)
        if video is None:
            continue
        cap = cv2.VideoCapture(str(video))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()
        shift = 0
        streams = body.get("streams", {})
        for name, st in streams.items():
            if stream.split("_")[-1] in name:
                shift = int(st.get("stream_properties", {}).get("sync", {}).get("frame_shift", 0))
        m = re.search(r"g([A-Z])[_/\\]?(\d+)", str(a).replace("\\", "/"))
        driver = f"dmd_g{m.group(1)}{m.group(2)}" if m else f"dmd_{norm(a.parent.name)}"
        for act in body.get("actions", {}).values():
            typ = act.get("type", "")
            if not typ.startswith("driver_actions/"):
                continue
            label = DMD_LABELS.get(norm(typ.split("/", 1)[1]))
            if label is None:
                continue
            for iv in act.get("frame_intervals", []):
                s, e = iv["frame_start"] + shift, iv["frame_end"] + shift
                out.append(Segment("dmd", driver, video, s / fps, (e + 1) / fps, label, stream))
    return out


# --------------------------------------------------------------------------- 100-Driver

DRIVER100_LABELS = {  # class-name keywords -> label; folders are matched by these words
    "drivesafe": "normal", "safedriving": "normal",
    "talkleft": "phone_left_ear", "talkright": "phone_right_ear",
    "textleft": "phone_in_hand", "textright": "phone_in_hand",
    "eatleft": "eating", "eatright": "eating",
    "drinkleft": "drinking", "drinkright": "drinking",
    "yawning": "neg_yawning",
}


def driver100(root: str | Path, cams: tuple[str, ...] = ("Cam4",),
              driver_regex: str = r"(P\d{3})") -> list[Still]:
    """100-Driver: images under <lighting>/<camera>/<class folder>/*.jpg. The class folder is
    matched by its NAME (e.g. 'C5_Talk_Right'), the driver id by `driver_regex` on the file
    name. Which camera is closest to a mirror mount must be confirmed from the dataset paper;
    `cams` is a parameter for that reason."""
    root = Path(root)
    out: list[Still] = []
    for img in root.rglob("*"):
        if img.suffix.lower() not in (".jpg", ".png", ".jpeg"):
            continue
        parts = img.relative_to(root).parts
        if cams and not any(c.lower() in (p.lower() for p in parts) for c in cams):
            continue
        cls = norm(re.sub(r"^c\d+[_\- ]*", "", img.parent.name, flags=re.I))
        label = DRIVER100_LABELS.get(cls)
        if label is None:
            continue
        m = re.search(driver_regex, img.name)
        driver = f"d100_{m.group(1)}" if m else f"d100_{norm(img.stem)[:8]}"
        view = next((p for p in parts if p.lower().startswith("cam")), "")
        out.append(Still("driver100", driver, img, label, view))
    if not out:
        raise FileNotFoundError(f"100-Driver: no labelled images under {root} for {cams}")
    return out


# --------------------------------------------------------------------------- YawDD


def yawdd(root: str | Path) -> list[Segment]:
    """YawDD mirror set: one video per driver and condition, named like
    '12-MaleGlasses-Talking.avi'. Whole videos are negatives (no objects). Labels come from
    the condition word in the file name."""
    import cv2

    root = Path(root)
    out: list[Segment] = []
    words = {"normal": "neg_normal", "talking": "neg_talking", "singing": "neg_singing",
             "yawning": "neg_yawning"}
    for v in sorted(root.rglob("*")):
        if v.suffix.lower() not in VIDEO_EXT:
            continue
        n = v.stem.lower()
        conds = [lab for w, lab in words.items() if w in n]
        if len(conds) != 1:  # e.g. "Talking&Yawning": ambiguous, skip
            continue
        m = re.match(r"(\d+)-?([A-Za-z]+)", v.stem)
        driver = f"yawdd_{m.group(1)}{m.group(2)[:1].lower()}" if m else f"yawdd_{norm(v.stem)}"
        cap = cv2.VideoCapture(str(v))
        dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / (cap.get(cv2.CAP_PROP_FPS) or 30.0)
        cap.release()
        out.append(Segment("yawdd", driver, v, 0.0, dur, conds[0], "mirror"))
    if not out:
        raise FileNotFoundError(f"YawDD: no labelled videos under {root}")
    return out


# --------------------------------------------------------------------------- our recordings

OURS_LABELS = {"talking": "neg_talking", "nod_turn": "normal", "elbow_on_door": "neg_hand_on_head",
               "hand_on_head": "neg_hand_on_head", "singing": "neg_singing"}


def ours(root: str | Path) -> list[Segment]:
    """Clips from scripts/record.py: <name>.mp4 + <name>.json with a prompt timeline."""
    root = Path(root)
    files = [root] if root.suffix.lower() in VIDEO_EXT else sorted(root.rglob("*.mp4"))
    out: list[Segment] = []
    for v in files:
        meta_p = v.with_suffix(".json")
        if not meta_p.is_file():
            continue
        meta = json.loads(meta_p.read_text(encoding="utf8"))
        for s in meta.get("timeline", []):
            out.append(Segment("ours", f"ours_{meta.get('subject', 'S00')}", v,
                               float(s["start"]), float(s["end"]),
                               OURS_LABELS.get(s["label"], s["label"]), "mirror"))
    if not out:
        raise FileNotFoundError(f"ours: no record.py clips with a timeline under {root}")
    return out


# --------------------------------------------------------------------------- clips (crop builder)


@dataclass(frozen=True)
class Clip:
    """One labelled action clip: a video file, or a folder of frame images (3MDAD)."""

    source: str
    driver: str
    label: str
    path: Path  # video file or frame folder
    fps: float = 30.0

    @property
    def name(self) -> str:
        return self.path.name

    def frames(self, every_s: float):
        """Yield (t_seconds, BGR frame) every `every_s` seconds."""
        import cv2

        if self.path.is_dir():
            imgs = sorted((p for p in self.path.iterdir()
                           if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp")),
                          key=lambda p: [int(x) for x in re.findall(r"\d+", p.stem)] or [0])
            step = max(1, round(every_s * self.fps))
            for i in range(0, len(imgs), step):
                img = cv2.imread(str(imgs[i]))
                if img is not None:
                    yield i / self.fps, img
            return
        cap = cv2.VideoCapture(str(self.path))
        fps = cap.get(cv2.CAP_PROP_FPS) or self.fps
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        step = max(1, round(every_s * fps))
        for i in range(0, n, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, img = cap.read()
            if not ok:
                break
            yield i / fps, img
        cap.release()


EBDD_LABELS = {"ATTENTIVE": "normal", "CELL_PHONE": "phone_unknown_ear", "EATING": "eating",
               "TEXT": "phone_in_hand", "UNATTENTIVE": "other_none"}


def ebdd(root: str | Path) -> list[Clip]:
    """EBDD (windshield camera facing the driver): <DRIVER>_<ACTIVITY>.mp4, e.g.
    AKKAS_CELL_PHONE.mp4. Which ear the phone is at is not labelled (resolved by the pose
    wrist in the crop builder)."""
    out = []
    for v in sorted(Path(root).rglob("*")):
        if v.suffix.lower() not in VIDEO_EXT:
            continue
        stem = re.sub(r"\s+", "", v.stem).upper()
        for key, label in EBDD_LABELS.items():
            if stem.endswith("_" + key):
                out.append(Clip("ebdd", f"ebdd_{stem[: -len(key) - 1].lower()}", label, v))
                break
    if not out:
        raise FileNotFoundError(f"EBDD: no <DRIVER>_<ACTIVITY>.mp4 clips under {root}")
    return out


MDAD3_LABELS = {1: "normal", 2: "hair_makeup", 3: "other_none", 4: "other_none",
                5: "phone_in_hand", 6: "phone_in_hand", 7: "phone_right_ear",
                8: "phone_left_ear", 10: "neg_talking", 11: "neg_singing", 13: "drinking",
                14: "drinking", 16: "smoking"}  # A9 picture, A12 fatigue, A15 reach: skipped


def mdad3_front(root: str | Path, view_token: str = "RGB2", fps: float = 30.0) -> list[Clip]:
    """3MDAD, front view (Kinect 2 = 'RGB2'), day RGB: frame-image folders per subject and
    action, identified by S<n> and A<n> / AC<n> tokens in the path (e.g. .../RGB2/S6/AC7/).
    A7 / A8 = talking on the phone with the right / left hand."""
    root = Path(root)
    groups: dict[Path, tuple[str, int]] = {}
    for img in root.rglob("*"):
        if img.suffix.lower() not in (".jpg", ".jpeg", ".png", ".bmp"):
            continue
        rel = str(img.relative_to(root)).replace("\\", "/")
        if view_token and view_token.lower() not in rel.lower():
            continue
        s = re.search(r"(?:^|[/_])S(?:UB)?(\d+)", rel, re.I)
        a = re.search(r"(?:^|[/_])AC?T?(\d+)(?:[/_.]|$)", rel, re.I)
        if s and a and img.parent not in groups:
            groups[img.parent] = (s.group(1), int(a.group(1)))
    out = [Clip("3mdad", f"3mdad_s{s}", MDAD3_LABELS[a], d, fps)
           for d, (s, a) in sorted(groups.items()) if a in MDAD3_LABELS]
    if not out:
        raise FileNotFoundError(f"3MDAD: no {view_token} frame folders with S<n>/A<n> under {root}")
    return out


ADAPTERS = {"syndd": syndd, "dmd": dmd, "driver100": driver100, "yawdd": yawdd, "ours": ours}
