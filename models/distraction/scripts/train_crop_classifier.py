#!/usr/bin/env python3
"""Train a crop classifier (ear: phone / hand_no_phone / none, or mouth: drink / food / none),
export it to NCNN, and score it on the held-out drivers through the NCNN runtime live.py uses.
TRAINING ENV (GPU).

    python scripts/build_crops.py --3mdad <front-view folder> --ebdd <EBDD folder>
    python scripts/train_crop_classifier.py --kind ear     # -> models/ear_cls_128_ncnn_model
    python scripts/train_crop_classifier.py --kind mouth   # -> models/mouth_cls_128_ncnn_model

YOLO26n-cls from ImageNet weights at 128 px, colour (configs/data.yaml look). Horizontal flip
on: a mirrored right-ear crop looks like a left-ear crop and the labels are side-neutral.
Writes <root>/runs/<kind>_cls_128/test_eval.json and test_contact_sheet.jpg (~30 held-out
crops per class, green = correct, red = wrong, with the predicted class).
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CLASSES = {"ear": ("hand_no_phone", "none", "phone"), "mouth": ("drink", "food", "none")}


def classifier(kind: str, weights: Path):
    from rtdms_distraction.config import EarClassifierConfig, MouthClassifierConfig
    from rtdms_distraction.ear_clf import EarClassifier, MouthClassifier

    if kind == "ear":
        return EarClassifier(EarClassifierConfig(enabled=True, weights=str(weights)))
    return MouthClassifier(MouthClassifierConfig(enabled=True, weights=str(weights)))


def evaluate(kind: str, weights: Path, test_dir: Path, sheet: Path | None, imgsz: int,
             per_class: int = 30, source: str | None = None):
    """Per-class P / R on test_dir; `source` keeps only crops named '<source>__*'."""
    clf = classifier(kind, weights)
    clf.imgsz = imgsz
    conf = Counter()
    tiles = {c: [] for c in CLASSES[kind]}
    rng = random.Random(0)
    for true in CLASSES[kind]:
        files = sorted((test_dir / true).glob(f"{source}__*.jpg" if source else "*.jpg"))
        show = set(rng.sample(range(len(files)), min(per_class, len(files))))
        for i, f in enumerate(files):
            img = cv2.imread(str(f))
            p = clf.probs(img)
            pred = clf.names[int(np.argmax(p))]
            conf[(true, pred)] += 1
            if sheet is not None and i in show:
                t = cv2.resize(img, (96, 96))
                col = (60, 200, 60) if pred == true else (40, 40, 230)
                cv2.rectangle(t, (0, 0), (95, 95), col, 3)
                cv2.putText(t, f"{pred[:6]} {p.max():.2f}", (3, 92), cv2.FONT_HERSHEY_SIMPLEX,
                            0.33, (255, 255, 255), 1, cv2.LINE_AA)
                tiles[true].append(t)
    if sheet is not None:
        cols = (per_class + 1) // 2  # each class: 2 rows of `cols` tiles
        blocks = []
        for c in CLASSES[kind]:
            t = tiles[c] + [np.zeros((96, 96, 3), np.uint8)] * (2 * cols - len(tiles[c]))
            grid = np.vstack([np.hstack(t[:cols]), np.hstack(t[cols:2 * cols])])
            head = np.zeros((192, 120, 3), np.uint8)
            cv2.putText(head, c, (4, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
            blocks.append(np.hstack([head, grid]))
        cv2.imwrite(str(sheet), np.vstack(blocks))
    out = {}
    for c in CLASSES[kind]:
        tp = conf[(c, c)]
        n_true = sum(v for (t, _), v in conf.items() if t == c)
        n_pred = sum(v for (_, pr), v in conf.items() if pr == c)
        out[c] = {"n": n_true, "precision": round(tp / n_pred, 3) if n_pred else None,
                  "recall": round(tp / n_true, 3) if n_true else None}
    f1 = [2 * v["precision"] * v["recall"] / (v["precision"] + v["recall"])
          if v["precision"] and v["recall"] else 0.0 for v in out.values()]
    out["macro_f1"] = round(float(np.mean(f1)), 3)
    out["confusion"] = {f"{t}->{pr}": v for (t, pr), v in sorted(conf.items())}
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--kind", choices=sorted(CLASSES), required=True)
    p.add_argument("--imgsz", type=int, default=128)
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--batch", type=int, default=128)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--eval-only", action="store_true")
    p.add_argument("--crops", default="crops", help="crops folder under the data root")
    p.add_argument("--grayscale", action="store_true",
                   help="crops are gray x3 (build_crops.py --grayscale): no hue / saturation aug")
    p.add_argument("--tag", default="",
                   help="run / model name suffix ('syndd' -> ear_cls_160_syndd); keeps older runs")
    p.add_argument("--report-source", action="append", default=[],
                   help="also score the test crops of this source alone (e.g. syndd); repeatable")
    args = p.parse_args()

    dcfg = yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))
    root = Path(dcfg["root"])
    data = root / args.crops / args.kind
    name = f"{args.kind}_cls_{args.imgsz}" + (f"_{args.tag}" if args.tag else "")
    for split in ("train", "val", "test"):
        missing = [c for c in CLASSES[args.kind] if not any((data / split / c).glob("*.jpg"))]
        if missing:
            raise SystemExit(f"{data / split} has no crops for {missing}: run build_crops.py")
    dest = ROOT / "models" / f"{name}_ncnn_model"
    run = root / "runs" / name
    if not args.eval_only:
        from ultralytics import YOLO

        colour = dcfg.get("look", "color") == "color" and not args.grayscale
        model = YOLO(str(ROOT / "models" / "yolo26n-cls.pt"))
        model.train(data=str(data), imgsz=args.imgsz, epochs=args.epochs, batch=args.batch,
                    workers=args.workers, project=str(root / "runs"), name=name, exist_ok=True,
                    seed=0, fliplr=0.5, hsv_h=0.015 if colour else 0.0,
                    hsv_s=0.5 if colour else 0.0, hsv_v=0.4)
        out = Path(YOLO(str(run / "weights" / "best.pt")).export(format="ncnn",
                                                                  imgsz=args.imgsz))
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(out), dest)
        print(f"NCNN -> {dest}")
    run.mkdir(parents=True, exist_ok=True)
    # val (held-out drivers) chooses between runs (e.g. crop size); test is only reported.
    val = evaluate(args.kind, dest, data / "val", None, args.imgsz)
    (run / "val_eval.json").write_text(json.dumps(val, indent=2), encoding="utf8", newline="\n")
    print("val", json.dumps(val, indent=2))
    res = evaluate(args.kind, dest, data / "test", run / "test_contact_sheet.jpg", args.imgsz)
    if args.kind == "mouth" and not (data / "HAND_CHECKED").exists():
        # 3MDAD drink labels (test drivers too) come from CLIP zero-shot (build_crops.py).
        res["test_labels"] = "CLIP-labelled test set (drink not hand-checked yet)"
    (run / "test_eval.json").write_text(json.dumps(res, indent=2), encoding="utf8", newline="\n")
    print("test", json.dumps(res, indent=2))
    print(f"contact sheet: {run / 'test_contact_sheet.jpg'}")
    for src in args.report_source:
        r = evaluate(args.kind, dest, data / "test", run / f"test_contact_sheet_{src}.jpg",
                     args.imgsz, source=src)
        (run / f"test_eval_{src}.json").write_text(json.dumps(r, indent=2), encoding="utf8",
                                                   newline="\n")
        print(f"test ({src} drivers only)", json.dumps(r, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
