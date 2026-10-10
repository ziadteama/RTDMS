#!/usr/bin/env python3
"""Export YOLO26 weights to NCNN (Pi runtime) and optionally ONNX. TRAINING ENV ONLY.

    python scripts/export_ncnn.py                                 # COCO yolo26n, imgsz 416
    python scripts/export_ncnn.py --weights runs/detect/train/weights/best.pt --name ft_v1 --onnx
    python scripts/export_ncnn.py --head one2one --name yolo26n_coco_416_o2o   # NMS-free head

--head one2one: Ultralytics refuses YOLO26's end-to-end export for NCNN (no TopK op). The
one-to-one branch has the same structure as the default one-to-many branch, so its weights are
copied into the exported path; the runtime then skips NMS (threshold + top-k), which is what the
end-to-end graph would have done. The export is tagged `rtdms_head: one2one` in metadata.yaml.

Output: models/<name>_ncnn_model/{model.ncnn.param, model.ncnn.bin, metadata.yaml}
(and models/<name>.onnx). Copy the NCNN folder to the Pi; the Pi needs only the `ncnn` wheel.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"


def use_one2one(model) -> None:
    """Put the one-to-one (NMS-free) branch's weights where the exporter reads the head."""
    head = model.model.model[-1]
    if getattr(head, "one2one_cv2", None) is None:
        raise SystemExit("this checkpoint has no one-to-one head (not a YOLO26/end-to-end model)")
    head.cv2, head.cv3 = head.one2one_cv2, head.one2one_cv3
    head.end2end = False  # export the raw (4 + nc) x anchors output; NMS-free decode at runtime


def tag(meta: Path, head: str) -> None:
    with open(meta, "a", encoding="utf8") as f:
        f.write(f"rtdms_head: {head}\n")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--weights", default=str(MODELS / "yolo26n.pt"),
                   help="a .pt file; 'yolo26n.pt' is downloaded by Ultralytics if missing")
    p.add_argument("--name", default="yolo26n_coco_416", help="output name under models/")
    p.add_argument("--imgsz", type=int, default=416)
    p.add_argument("--onnx", action="store_true", help="also export ONNX")
    p.add_argument("--half", action="store_true", help="fp16 NCNN weights")
    p.add_argument("--head", choices=["one2many", "one2one"], default="one2many",
                   help="which YOLO26 head to export (one2one = NMS-free)")
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

    if args.head == "one2one":
        use_one2one(model)
    extra = {"half": True} if args.half else {}
    out = Path(model.export(format="ncnn", imgsz=args.imgsz, **extra))
    dest = MODELS / f"{args.name}_ncnn_model"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(out), dest)
    tag(dest / "metadata.yaml", args.head)
    print(f"NCNN -> {dest}")
    for f in sorted(dest.iterdir()):
        print(f"   {f.name:28s} {f.stat().st_size / 1e6:6.2f} MB")

    if args.onnx:
        m = YOLO(str(weights))
        if args.head == "one2one":
            use_one2one(m)
        # Default nms=None keeps the raw head (nms=False would request the end-to-end graph).
        onnx = Path(m.export(format="onnx", imgsz=args.imgsz, simplify=True))
        dest_onnx = MODELS / f"{args.name}.onnx"
        shutil.move(str(onnx), dest_onnx)
        shutil.copy(dest / "metadata.yaml", dest_onnx.with_suffix(".metadata.yaml"))
        print(f"ONNX -> {dest_onnx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
