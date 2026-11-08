#!/usr/bin/env python3
"""Build a balanced Open Images V7 subset for phone / drink / food / hand.

    python scripts/build_openimages.py                 # all steps, resumable
    python scripts/build_openimages.py --step filter   # only stream + filter the box CSVs

Steps (each cached under <root>/openimages/):
  filter    stream the official box CSVs (train is 2.3 GB) and keep only rows for our classes,
            people and faces. The full CSV is never written to disk.
  select    per split, choose images class-balanced up to cap_*; rank images where the object
            is near a face or touching a hand first, then images with a person, then the rest.
            Images whose boxes for our classes are group boxes or depictions are skipped.
  download  fetch from the public CVDF S3 mirror, resize to max_side, write JPEG + YOLO labels
            (labels_gt/) + face boxes (faces.json, used later for head-and-shoulders crops).

Open Images is not exhaustively labelled for every class in every image; scripts/teacher_label.py
fills the gaps afterwards.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://storage.googleapis.com/openimages"
CSVS = {
    "train": f"{BASE}/v6/oidv6-train-annotations-bbox.csv",
    "validation": f"{BASE}/v5/validation-annotations-bbox.csv",
    "test": f"{BASE}/v5/test-annotations-bbox.csv",
}
CLASS_DESC = f"{BASE}/v7/oidv7-class-descriptions-boxable.csv"
IMG_URL = "https://s3.amazonaws.com/open-images-dataset/{split}/{id}.jpg"
OUR_SPLIT = {"train": "train", "validation": "val", "test": "test"}


def load_cfg():
    cfg = yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))
    return cfg, Path(cfg["root"]) / "openimages"


def mids(cfg) -> tuple[dict[str, str], set[str], str]:
    """-> (mid -> our class or 'person'/'face'), name lookup."""
    text = requests.get(CLASS_DESC, timeout=60).text
    name_to_mid = {name: mid for mid, name in csv.reader(io.StringIO(text))}
    oi = cfg["openimages"]
    out = {}
    for name, ours in oi["class_map"].items():
        out[name_to_mid[name]] = ours
    for name in oi["person_classes"]:
        out[name_to_mid[name]] = "person"
    out[name_to_mid[oi["face_class"]]] = "face"
    return out


# --------------------------------------------------------------------------- filter


def stream_lines(url: str, retries: int = 20):
    """Yield text lines of a large remote file; on a dropped connection resume with an HTTP
    Range request from the first byte not yet yielded (only complete lines are yielded)."""
    offset = 0
    for attempt in range(retries + 1):
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        try:
            with requests.get(url, stream=True, timeout=120, headers=headers) as r:
                r.raise_for_status()
                if offset and r.status_code != 206:
                    raise RuntimeError("server ignored the Range request; cannot resume")
                buf = b""
                for chunk in r.iter_content(chunk_size=1 << 20):
                    buf += chunk
                    *lines, buf = buf.split(b"\n")
                    for ln in lines:
                        offset += len(ln) + 1
                        yield ln.decode("utf8").rstrip("\r")
                if buf:
                    offset += len(buf)
                    yield buf.decode("utf8").rstrip("\r")
                return
        except (requests.RequestException, ConnectionError) as e:
            print(f"[filter] connection dropped at byte {offset} ({type(e).__name__}); "
                  f"resuming ({attempt + 1}/{retries})", flush=True)
            time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"gave up on {url} after {retries} resumes")


def step_filter(cfg, out: Path) -> None:
    keep = mids(cfg)
    meta = out / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    for split, url in CSVS.items():
        dest = meta / f"{split}_boxes.csv"
        if dest.is_file():
            print(f"[filter] {split}: cached")
            continue
        t0 = time.time()
        n_in = n_out = 0
        tmp = dest.with_suffix(".part")
        with open(tmp, "w", newline="", encoding="utf8") as f:
            w = csv.writer(f)
            w.writerow(["ImageID", "cls", "XMin", "XMax", "YMin", "YMax", "IsGroupOf",
                        "IsDepiction"])
            col = None
            for line in stream_lines(url):
                if col is None:
                    col = {c: i for i, c in enumerate(line.split(","))}
                    continue
                n_in += 1
                parts = line.split(",")
                cls = keep.get(parts[col["LabelName"]])
                if cls is None:
                    continue
                w.writerow([parts[col["ImageID"]], cls, parts[col["XMin"]], parts[col["XMax"]],
                            parts[col["YMin"]], parts[col["YMax"]], parts[col["IsGroupOf"]],
                            parts[col["IsDepiction"]]])
                n_out += 1
                if n_in % 2_000_000 == 0:
                    print(f"[filter] {split}: {n_in / 1e6:.0f}M rows read, {n_out} kept, "
                          f"{time.time() - t0:.0f}s", flush=True)
        tmp.replace(dest)
        print(f"[filter] {split}: {n_in} rows -> {n_out} kept in {time.time() - t0:.0f}s")


# --------------------------------------------------------------------------- select


def load_boxes(path: Path) -> dict[str, list[tuple]]:
    imgs: dict[str, list[tuple]] = defaultdict(list)
    with open(path, encoding="utf8") as f:
        for row in csv.DictReader(f):
            imgs[row["ImageID"]].append((row["cls"], float(row["XMin"]), float(row["YMin"]),
                                         float(row["XMax"]), float(row["YMax"]),
                                         row["IsGroupOf"] == "1", row["IsDepiction"] == "1"))
    return imgs


def near(a, b, margin: float) -> bool:
    """Boxes (x1, y1, x2, y2) overlap or come within `margin` (normalised units)."""
    return not (a[2] + margin < b[0] or b[2] + margin < a[0] or a[3] + margin < b[1]
                or b[3] + margin < a[1])


def rank(boxes: list[tuple]) -> int:
    """2 = object held near a face / touching a hand, 1 = a person in the image, 0 = other."""
    faces = [b[1:5] for b in boxes if b[0] == "face"]
    hands = [b[1:5] for b in boxes if b[0] == "hand"]
    objs = [b[1:5] for b in boxes if b[0] in ("phone", "drink", "food")]
    for o in objs:
        for fc in faces:
            if near(o, fc, 0.5 * (fc[2] - fc[0])):
                return 2
        if any(near(o, h, 0.0) for h in hands):
            return 2
    return 1 if faces or any(b[0] == "person" for b in boxes) else 0


def step_select(cfg, out: Path) -> None:
    oi = cfg["openimages"]
    classes = cfg["classes"]
    rng = random.Random(0)
    for split, ours in OUR_SPLIT.items():
        dest = out / "meta" / f"{ours}_selection.json"
        if dest.is_file():
            print(f"[select] {ours}: cached")
            continue
        cap = oi[f"cap_{ours}"]
        imgs = load_boxes(out / "meta" / f"{split}_boxes.csv")
        cand: dict[str, list[tuple[int, float, str]]] = {c: [] for c in classes}
        for iid, boxes in imgs.items():
            ourb = [b for b in boxes if b[0] in classes]
            if not ourb or any(b[5] or b[6] for b in ourb):  # group boxes / drawings
                continue
            r = rank(boxes)
            for c in {b[0] for b in ourb}:
                cand[c].append((r, rng.random(), iid))
        for c in cand:
            cand[c].sort(key=lambda x: (-x[0], x[1]))
        counts = dict.fromkeys(classes, 0)
        chosen: dict[str, None] = {}
        # Rarest class first, so common classes (hand) fill up from images already chosen.
        for c in sorted(classes, key=lambda k: len(cand[k])):
            for _, _, iid in cand[c]:
                if counts[c] >= cap:
                    break
                if iid in chosen:
                    continue
                chosen[iid] = None
                for k in {b[0] for b in imgs[iid] if b[0] in classes}:
                    counts[k] += 1
        sel = {iid: imgs[iid] for iid in chosen}
        dest.write_text(json.dumps(sel), encoding="utf8")
        avail = {c: len(v) for c, v in cand.items()}
        print(f"[select] {ours}: {len(sel)} images; images per class {counts}; "
              f"candidates {avail}")


# --------------------------------------------------------------------------- download


def fetch(session, split: str, iid: str, max_side: int, img_path: Path) -> bool:
    if img_path.is_file():
        return True
    for attempt in range(3):
        try:
            r = session.get(IMG_URL.format(split=split, id=iid), timeout=30)
            if r.status_code != 200:
                return False
            img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return False
            h, w = img.shape[:2]
            s = max_side / max(h, w)
            if s < 1:
                img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(img_path), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            return True
        except (requests.RequestException, OSError):
            time.sleep(1 + attempt)
    return False


def step_download(cfg, out: Path, workers: int) -> None:
    classes = cfg["classes"]
    max_side = cfg["openimages"]["max_side"]
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=workers))
    for split, ours in OUR_SPLIT.items():
        sel = json.loads((out / "meta" / f"{ours}_selection.json").read_text(encoding="utf8"))
        img_dir, lab_dir = out / "images" / ours, out / "labels_gt" / ours
        img_dir.mkdir(parents=True, exist_ok=True)
        lab_dir.mkdir(parents=True, exist_ok=True)
        faces = {}
        ok = fail = 0
        t0 = time.time()
        with ThreadPoolExecutor(workers) as ex:
            futs = {ex.submit(fetch, session, split, iid, max_side, img_dir / f"{iid}.jpg"): iid
                    for iid in sel}
            for i, fu in enumerate(as_completed(futs), 1):
                iid = futs[fu]
                if not fu.result():
                    fail += 1
                    continue
                ok += 1
                lines = []
                for c, x1, y1, x2, y2, *_ in sel[iid]:
                    if c in classes:
                        lines.append(f"{classes.index(c)} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} "
                                     f"{x2 - x1:.6f} {y2 - y1:.6f}")
                (lab_dir / f"{iid}.txt").write_text("\n".join(lines) + "\n", encoding="utf8")
                faces[iid] = [b[1:5] for b in sel[iid] if b[0] == "face"]
                if i % 1000 == 0:
                    print(f"[download] {ours}: {i}/{len(sel)} ({time.time() - t0:.0f}s)",
                          flush=True)
        (out / "meta" / f"{ours}_faces.json").write_text(json.dumps(faces), encoding="utf8")
        print(f"[download] {ours}: {ok} ok, {fail} failed in {time.time() - t0:.0f}s")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--step", choices=["filter", "select", "download", "all"], default="all")
    p.add_argument("--workers", type=int, default=16)
    args = p.parse_args()
    cfg, out = load_cfg()
    out.mkdir(parents=True, exist_ok=True)
    if args.step in ("filter", "all"):
        step_filter(cfg, out)
    if args.step in ("select", "all"):
        step_select(cfg, out)
    if args.step in ("download", "all"):
        step_download(cfg, out, args.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
