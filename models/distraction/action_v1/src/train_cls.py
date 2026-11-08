"""Steps 4 / 5: train an Ultralytics classifier on a folder dataset (train/ val/ <class>/ *.jpg)
with the extra crop augmentations of augment.py. Resumes from last.pt if a run was interrupted.

python train_cls.py <data dir> <run name> [model=yolo26n-cls.pt] [imgsz=224] [epochs=40] [batch=128]
"""
import os
import sys
from pathlib import Path

import torchvision.transforms as T
from ultralytics import YOLO
from ultralytics.models.yolo.classify import ClassificationTrainer

import ultralytics.models.yolo.classify.train as cls_train
from ultralytics.data import build as ul_build

from augment import CropAug

# Pinned host memory failed on this laptop during the first validation pass
# (CUDA_ERROR_ALREADY_MAPPED from cuMemHostAlloc), so loaders run without it.
cls_train.build_dataloader = lambda *a, **k: ul_build.build_dataloader(*a, **{**k, "pin_memory": False})

RUNS = Path("D:/rtdms-data/action_v1/runs")
BASE = Path(r"C:\Users\youss\projects\RTDMS\models")


class AugTrainer(ClassificationTrainer):
    def build_dataset(self, img_path, mode="train", batch=None):
        ds = super().build_dataset(img_path, mode, batch)
        if mode == "train":
            ds.torch_transforms = T.Compose([CropAug(), ds.torch_transforms])
        return ds


def main():
    data, name = sys.argv[1], sys.argv[2]
    model = sys.argv[3] if len(sys.argv) > 3 else "yolo26n-cls.pt"
    imgsz = int(sys.argv[4]) if len(sys.argv) > 4 else 224
    epochs = int(sys.argv[5]) if len(sys.argv) > 5 else 40
    batch = int(sys.argv[6]) if len(sys.argv) > 6 else 128
    last = RUNS / name / "weights" / "last.pt"
    if last.exists():
        print(f"resuming {last}", flush=True)
        YOLO(str(last)).train(resume=True, trainer=AugTrainer)
        return
    w = BASE / model if (BASE / model).exists() else model
    YOLO(str(w)).train(
        data=data, trainer=AugTrainer, imgsz=imgsz, epochs=epochs, batch=batch, patience=8,
        project=str(RUNS), name=name, exist_ok=True, workers=int(os.environ.get("WORKERS", "8")), seed=0, deterministic=False,
        fliplr=0.5, scale=0.2, erasing=0.4, auto_augment=None, hsv_h=0, hsv_s=0, hsv_v=0,
        cos_lr=True, lr0=0.001, optimizer="AdamW", warmup_epochs=1,
        cache=False, plots=True, amp=True)


if __name__ == "__main__":
    main()
