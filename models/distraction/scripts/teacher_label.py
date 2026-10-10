#!/usr/bin/env python3
"""Fill missing labels with large teacher models. TRAINING ENV ONLY (GPU).

    python scripts/teacher_label.py --images D:/rtdms-data/openimages/images/train \
        --gt D:/rtdms-data/openimages/labels_gt/train --out D:/rtdms-data/openimages/labels/train
    python scripts/teacher_label.py --images D:/rtdms-data/syndd/frames/train --out ...  # no GT

Teachers (configs/data.yaml -> teacher):
  COCO      yolo26m at imgsz 1280 with test-time augmentation -> phone, drink (cup, bottle,
            wine glass) and COCO foods
  open-vocab YOLOE-26l with text prompts -> food, hand
A teacher box is added only when no box of the same class (ground truth or already added)
overlaps it by dedup_iou. Output: YOLO labels, plus labels_meta/<id>.json recording the source
and confidence of every box, which the review sample and the quality statistics use.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COCO_TO_OURS = {"cell phone": "phone", "cup": "drink", "bottle": "drink", "wine glass": "drink",
                "banana": "food", "apple": "food", "sandwich": "food", "orange": "food",
                "hot dog": "food", "pizza": "food", "donut": "food", "cake": "food"}


def iou(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def read_yolo(path: Path) -> list[tuple[int, float, float, float, float]]:
    """-> [(cls, x1, y1, x2, y2)] normalised."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf8").split("\n"):
        if line.strip():
            c, cx, cy, w, h = line.split()
            cx, cy, w, h = float(cx), float(cy), float(w), float(h)
            out.append((int(c), cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
    return out


def write_yolo(path: Path, boxes) -> None:
    lines = [f"{c} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}"
             for c, x1, y1, x2, y2 in boxes]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--images", required=True)
    p.add_argument("--gt", help="existing YOLO labels to keep (optional)")
    p.add_argument("--out", required=True, help="merged YOLO labels dir")
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--limit", type=int, help="only the first N images (smoke test)")
    p.add_argument("--no-tta", action="store_true")
    args = p.parse_args()

    from ultralytics import YOLO, YOLOE

    cfg = yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))
    t = cfg["teacher"]
    classes = cfg["classes"]
    imgs = sorted(Path(args.images).glob("*.jpg"))[: args.limit]
    if not imgs:
        raise SystemExit(f"no .jpg images in {args.images}")
    out = Path(args.out)
    meta_dir = out.parent.parent / "labels_meta" / out.name
    out.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    models_dir = ROOT / "models"

    # Start from ground truth.
    boxes = {}
    for im in imgs:
        gt = read_yolo(Path(args.gt) / f"{im.stem}.txt") if args.gt else []
        boxes[im.stem] = [{"cls": c, "box": b, "src": "gt", "conf": 1.0} for c, *b in gt]

    def add(stem, cls_name, xyxyn, conf, src):
        c = classes.index(cls_name)
        if any(e["cls"] == c and iou(e["box"], xyxyn) >= t["dedup_iou"] for e in boxes[stem]):
            return
        boxes[stem].append({"cls": c, "box": [round(v, 6) for v in xyxyn], "src": src,
                            "conf": round(conf, 3)})

    coco = YOLO(str(models_dir / t["coco_model"]))
    names = coco.names
    for res in coco.predict([str(i) for i in imgs], imgsz=t["coco_imgsz"], conf=t["coco_conf"],
                            augment=not args.no_tta, batch=args.batch, stream=True,
                            verbose=False):
        stem = Path(res.path).stem
        b = res.boxes
        for xy, cf, k in zip(b.xyxyn.cpu().numpy().tolist(), b.conf.cpu().numpy().tolist(),
                             b.cls.cpu().numpy().tolist(), strict=True):
            ours = COCO_TO_OURS.get(names[int(k)])
            if ours:
                add(stem, ours, xy, cf, "teacher_coco")
    print(f"[teacher] COCO teacher done on {len(imgs)} images", flush=True)

    ov = YOLOE(str(models_dir / t["open_vocab_model"]))
    prompts, prompt_cls = [], []
    for ours, words in t["open_vocab_prompts"].items():
        prompts += words
        prompt_cls += [ours] * len(words)
    try:
        ov.set_classes(prompts, ov.get_text_pe(prompts))
    except TypeError:  # newer Ultralytics computes the embeddings itself
        ov.set_classes(prompts)
    for res in ov.predict([str(i) for i in imgs], imgsz=t["coco_imgsz"],
                          conf=t["open_vocab_conf"], batch=args.batch, stream=True,
                          verbose=False):
        stem = Path(res.path).stem
        b = res.boxes
        for xy, cf, k in zip(b.xyxyn.cpu().numpy().tolist(), b.conf.cpu().numpy().tolist(),
                             b.cls.cpu().numpy().tolist(), strict=True):
            add(stem, prompt_cls[int(k)], xy, cf, "teacher_yoloe")
    print("[teacher] open-vocab teacher done", flush=True)

    counts: dict[str, dict[str, int]] = {}
    for stem, bl in boxes.items():
        write_yolo(out / f"{stem}.txt", [(e["cls"], *e["box"]) for e in bl])
        (meta_dir / f"{stem}.json").write_text(json.dumps(bl), encoding="utf8")
        for e in bl:
            d = counts.setdefault(classes[e["cls"]], {})
            d[e["src"]] = d.get(e["src"], 0) + 1
    summary = {"images": len(imgs), "boxes_by_class_and_source": counts}
    (meta_dir.parent / f"{out.name}_teacher_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
