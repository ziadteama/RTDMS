#!/usr/bin/env python3
"""Fine-tune YOLO26n (COCO weights) on the assembled dataset. TRAINING ENV ONLY (GPU).

    python scripts/train.py --data D:/rtdms-data/datasets/v1/data.yaml --imgsz 416 --name v1_416
    python scripts/train.py --data ... --imgsz 512 --name v1_512

Images are already grayscale x3 (offline conversion); colour jitter is off so they stay gray.
Horizontal flip stays ON: the classes are side-neutral, left/right is decided by the rules.
IRTrainer adds the IR photometric augmentation on top of Ultralytics' geometric ones.
Runs land in <root>/runs/<name>; best.pt is then exported with scripts/export_ncnn.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--data", required=True)
    p.add_argument("--imgsz", type=int, default=416)
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--name", required=True)
    p.add_argument("--weights", default=str(ROOT / "models" / "yolo26n.pt"))
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--patience", type=int, default=15)
    args = p.parse_args()

    from ultralytics import YOLO

    from rtdms_distraction.training import IRTrainer

    root = Path(yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))["root"])
    model = YOLO(args.weights)
    model.train(
        trainer=IRTrainer, data=args.data, imgsz=args.imgsz, epochs=args.epochs,
        batch=args.batch, workers=args.workers, patience=args.patience,
        project=str(root / "runs"), name=args.name, exist_ok=True, seed=0, deterministic=False,
        # grayscale: no hue / saturation jitter; brightness jitter is fine
        hsv_h=0.0, hsv_s=0.0, hsv_v=0.3,
        fliplr=0.5, flipud=0.0, degrees=5.0, translate=0.1, scale=0.5,
        mosaic=1.0, close_mosaic=10, mixup=0.0,
        plots=True, val=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
