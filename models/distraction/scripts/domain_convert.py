#!/usr/bin/env python3
"""Convert a labelled image set to our camera's look (offline augmentation).

    # Open Images (photos): head-and-shoulders crop + fisheye + occlusion + IR look
    python scripts/domain_convert.py --src D:/rtdms-data/openimages --split train --variants 2 \
        --faces D:/rtdms-data/openimages/meta/train_faces.json --out D:/rtdms-data/converted/oiv
    # in-car video frames (YawDD, SynDD): already framed like a driver ROI -> no crop
    python scripts/domain_convert.py --src D:/rtdms-data/yawdd --split all --no-crop \
        --out D:/rtdms-data/converted/yawdd

Input:  <src>/images/<split>/*.jpg and <src>/labels/<split>/*.txt (YOLO; missing = background)
Output: <out>/images/<split>/<stem>_v<k>.jpg + <out>/labels/<split>/<stem>_v<k>.txt
val/test get exactly one deterministic variant. With --calib, the real lens's distortion
coefficients replace the generic equidistant model.
"""

from __future__ import annotations

import argparse
import json
import sys
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rtdms_distraction.calibration import FisheyeCalibration  # noqa: E402
from rtdms_distraction.domain import convert  # noqa: E402


def read_labels(p: Path, w: int, h: int):
    out = []
    if p.is_file():
        for line in p.read_text(encoding="utf8").split("\n"):
            if line.strip():
                c, cx, cy, bw, bh = line.split()
                cx, cy, bw, bh = float(cx) * w, float(cy) * h, float(bw) * w, float(bh) * h
                out.append((int(c), cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2))
    return out


def write_labels(p: Path, boxes, w: int, h: int) -> None:
    lines = [f"{c} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} "
             f"{(y2 - y1) / h:.6f}" for c, x1, y1, x2, y2 in boxes]
    with open(p, "w", encoding="utf8", newline="\n") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def work(job):
    img_path, lab_path, out_img, out_lab, faces, variants, seed, opts = job
    img = cv2.imread(str(img_path))
    if img is None:
        return 0
    h, w = img.shape[:2]
    boxes = read_labels(lab_path, w, h)
    calib = FisheyeCalibration.load(opts["calib"]) if opts["calib"] else None
    n = 0
    for k in range(variants):
        rng = np.random.default_rng(seed + k)
        o, b = convert(img, boxes, faces, rng, out_size=opts["size"], crop=opts["crop"],
                       p_barrel=opts["p_barrel"], p_occlude=opts["p_occlude"], calib=calib)
        stem = f"{img_path.stem}_v{k}"
        cv2.imwrite(str(out_img / f"{stem}.jpg"), o, [cv2.IMWRITE_JPEG_QUALITY, 90])
        write_labels(out_lab / f"{stem}.txt", b, o.shape[1], o.shape[0])
        n += 1
    return n


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--src", required=True)
    p.add_argument("--split", required=True,
                   help="folder under images/: train | val | test | all (driver datasets)")
    p.add_argument("--out", required=True)
    p.add_argument("--labels-dir", default="labels", help="labels folder name under --src")
    p.add_argument("--faces", help="faces.json from build_openimages.py")
    p.add_argument("--variants", type=int, default=1, help="variants per TRAIN image")
    p.add_argument("--size", type=int, default=640)
    p.add_argument("--no-crop", action="store_true")
    p.add_argument("--p-barrel", type=float, default=0.5)
    p.add_argument("--p-occlude", type=float, default=0.5)
    p.add_argument("--calib", help="our fisheye calibration YAML (K, D)")
    p.add_argument("--workers", type=int, default=8)
    args = p.parse_args()

    src, out = Path(args.src), Path(args.out)
    splits = [args.split]
    faces = json.loads(Path(args.faces).read_text(encoding="utf8")) if args.faces else {}
    opts = {"size": args.size, "crop": not args.no_crop, "p_barrel": args.p_barrel,
            "p_occlude": args.p_occlude, "calib": args.calib}
    for split in splits:
        img_dir = src / "images" / split
        if not img_dir.is_dir():
            print(f"skip {split}: {img_dir} missing")
            continue
        oi, ol = out / "images" / split, out / "labels" / split
        oi.mkdir(parents=True, exist_ok=True)
        ol.mkdir(parents=True, exist_ok=True)
        variants = args.variants if split == "train" else 1
        jobs = []
        for im in sorted(img_dir.glob("*.jpg")):
            # Seed from the file name: reruns reproduce the same conversion.
            seed = zlib.crc32(im.stem.encode()) * 7 + (0 if split == "train" else 10_000)
            jobs.append((im, src / args.labels_dir / split / f"{im.stem}.txt", oi, ol,
                         faces.get(im.stem, []), variants, seed, opts))
        with ProcessPoolExecutor(args.workers) as ex:
            n = sum(ex.map(work, jobs, chunksize=32))
        print(f"{split}: {len(jobs)} images -> {n} converted into {oi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
