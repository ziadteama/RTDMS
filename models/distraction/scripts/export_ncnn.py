#!/usr/bin/env python3
"""Export YOLO26 weights to NCNN (Pi runtime) and optionally ONNX. TRAINING ENV ONLY.

    python scripts/export_ncnn.py                                 # COCO yolo26n, imgsz 416
    python scripts/export_ncnn.py --weights runs/detect/train/weights/best.pt --name ft_v1 --onnx

Output: models/<name>_ncnn_model/{model.ncnn.param, model.ncnn.bin, metadata.yaml}
(and models/<name>.onnx). Copy the NCNN folder to the Pi; the Pi needs only the `ncnn` wheel.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--weights", default=str(MODELS / "yolo26n.pt"),
                   help="a .pt file; 'yolo26n.pt' is downloaded by Ultralytics if missing")
    p.add_argument("--name", default="yolo26n_coco_416", help="output name under models/")
    p.add_argument("--imgsz", type=int, default=416)
    p.add_argument("--onnx", action="store_true", help="also export ONNX")
    p.add_argument("--half", action="store_true", help="fp16 NCNN weights")
    args = p.parse_args()

    from ultralytics import YOLO

    MODELS.mkdir(exist_ok=True)
    weights = Path(args.weights)
    if not weights.is_file():
        # Ultralytics resolves bare asset names (yolo26n.pt) by downloading into the CWD.
        model = YOLO(weights.name)
        downloaded = Path(model.ckpt_path)
        if downloaded.resolve() != weights.resolve():
            weights.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(downloaded), weights)
        model = YOLO(str(weights))
    else:
        model = YOLO(str(weights))

    out = Path(model.export(format="ncnn", imgsz=args.imgsz, half=args.half))
    dest = MODELS / f"{args.name}_ncnn_model"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(out), dest)
    print(f"NCNN -> {dest}")
    for f in sorted(dest.iterdir()):
        print(f"   {f.name:28s} {f.stat().st_size / 1e6:6.2f} MB")

    if args.onnx:
        onnx = Path(YOLO(str(weights)).export(format="onnx", imgsz=args.imgsz, simplify=True))
        dest_onnx = MODELS / f"{args.name}.onnx"
        shutil.move(str(onnx), dest_onnx)
        print(f"ONNX -> {dest_onnx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
