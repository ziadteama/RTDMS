#!/usr/bin/env python3
"""Train YOLOv8n-cls on collapsed safe/phone/eating folders (laptop only).

Primary dataset: State Farm Distracted Driver (Kaggle). AUC is deferred.

Example layout after prepare:
  data/collapsed/train/{safe,phone,eating}/*.jpg
  data/collapsed/val/{safe,phone,eating}/*.jpg

  python tools/train_cls.py --data data/collapsed --epochs 30 --imgsz 224
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description="Train YOLOv8n-cls for dms-phone")
    p.add_argument("--data", type=Path, required=True, help="ImageFolder root with train/ and val/")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--imgsz", type=int, default=224)
    p.add_argument("--out", type=Path, default=Path("models/phone_cls.pt"))
    args = p.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("Install train extras: pip install -e \".[train]\"") from exc

    model = YOLO("yolov8n-cls.pt")
    model.train(data=str(args.data), epochs=args.epochs, imgsz=args.imgsz, workers=2)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(args.out))
    print(f"saved weights hint → {args.out}")
    print("Next: python tools/export_onnx.py --weights", args.out)


if __name__ == "__main__":
    main()
