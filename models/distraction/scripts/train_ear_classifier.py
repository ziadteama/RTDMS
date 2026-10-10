#!/usr/bin/env python3
"""Train the ear-crop classifier (phone / hand_no_phone / none), export it to NCNN, and score it
on the held-out drivers through the same NCNN runtime the pipeline uses. TRAINING ENV (GPU).

    python scripts/build_ear_crops.py --statefarm data/public/statefarm
    python scripts/train_ear_classifier.py                      # -> models/ear_cls_128_ncnn_model

YOLO26n-cls from ImageNet weights at 128 px, colour (configs/data.yaml look). Horizontal flip
stays on: a right-ear crop mirrored looks like a left-ear crop, and the label is side-neutral.
After export, enable it with ear_classifier.enabled: true (already set in the laptop profile).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rtdms_distraction.config import EarClassifierConfig  # noqa: E402

CLASSES = ("hand_no_phone", "none", "phone")  # Ultralytics sorts class folders alphabetically


def evaluate(weights_dir: Path, test_dir: Path) -> dict:
    """Per-class precision / recall on test crops with the NCNN runtime (EarClassifier)."""
    from rtdms_distraction.ear_clf import EarClassifier

    clf = EarClassifier(EarClassifierConfig(enabled=True, weights=str(weights_dir)))
    conf = Counter()
    for true in CLASSES:
        for f in sorted((test_dir / true).glob("*.jpg")):
            p = clf.probs(cv2.imread(str(f)))
            conf[(true, clf.names[int(np.argmax(p))])] += 1
    out = {}
    for c in CLASSES:
        tp = conf[(c, c)]
        n_true = sum(v for (t, _), v in conf.items() if t == c)
        n_pred = sum(v for (_, pr), v in conf.items() if pr == c)
        out[c] = {"n": n_true, "precision": round(tp / n_pred, 3) if n_pred else None,
                  "recall": round(tp / n_true, 3) if n_true else None}
    out["confusion"] = {f"{t}->{pr}": v for (t, pr), v in sorted(conf.items())}
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--imgsz", type=int, default=128)
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--batch", type=int, default=128)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--name", default="ear_cls_128")
    p.add_argument("--eval-only", action="store_true")
    args = p.parse_args()

    dcfg = yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))
    root = Path(dcfg["root"])
    data = root / "ear_crops"
    for split in ("train", "val", "test"):
        missing = [c for c in CLASSES if not any((data / split / c).glob("*.jpg"))]
        if missing:
            raise SystemExit(f"{data / split} has no crops for {missing}: "
                             "run scripts/build_ear_crops.py --statefarm <path> first")
    dest = ROOT / "models" / f"{args.name}_ncnn_model"
    if not args.eval_only:
        from ultralytics import YOLO

        colour = dcfg.get("look", "color") == "color"
        model = YOLO(str(ROOT / "models" / "yolo26n-cls.pt"))  # downloaded if missing
        model.train(data=str(data), imgsz=args.imgsz, epochs=args.epochs, batch=args.batch,
                    workers=args.workers, project=str(root / "runs"), name=args.name,
                    exist_ok=True, seed=0, fliplr=0.5,
                    hsv_h=0.015 if colour else 0.0, hsv_s=0.5 if colour else 0.0, hsv_v=0.4)
        best = root / "runs" / args.name / "weights" / "best.pt"
        out = Path(YOLO(str(best)).export(format="ncnn", imgsz=args.imgsz))
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(out), dest)
        print(f"NCNN -> {dest}")
    res = evaluate(dest, data / "test")
    print(json.dumps(res, indent=2))
    (root / "runs" / args.name).mkdir(parents=True, exist_ok=True)
    (root / "runs" / args.name / "test_eval.json").write_text(json.dumps(res, indent=2),
                                                              encoding="utf8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
