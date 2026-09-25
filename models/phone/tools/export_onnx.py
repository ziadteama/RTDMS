#!/usr/bin/env python3
"""Export trained cls weights to ONNX for Pi ONNX Runtime."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--weights", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("models/phone_cls.onnx"))
    p.add_argument("--imgsz", type=int, default=224)
    args = p.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("Install train extras: pip install -e \".[train]\"") from exc

    model = YOLO(str(args.weights))
    model.export(format="onnx", imgsz=args.imgsz, simplify=True)
    print("Move/rename the exported .onnx to", args.out)
    print("Deploy that file to the Pi; do not install ultralytics on the Pi.")


if __name__ == "__main__":
    main()
