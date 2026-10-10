"""Ultralytics trainer with our camera's photometric augmentation added. TRAINING ENV ONLY.

Lives in the package (not in a script) so Windows dataloader workers, which re-import by name,
can unpickle it.
"""

from __future__ import annotations

import numpy as np
from ultralytics.data.dataset import YOLODataset
from ultralytics.models.yolo.detect import DetectionTrainer

from .domain import ir_look


class IRPhotometric:
    """Training-time IR look (noise, blur, low contrast, vignetting, resolution loss) on top of
    the offline conversion, so every epoch sees a different degradation of the same image.
    Photometric only: boxes are untouched."""

    def __init__(self, p: float = 0.5, strength: float = 0.6):
        self.p, self.strength = p, strength

    def __call__(self, labels: dict) -> dict:
        rng = np.random.default_rng()
        if rng.random() < self.p:
            labels["img"] = ir_look(labels["img"], rng, self.strength)
        return labels


class IRDataset(YOLODataset):
    def build_transforms(self, hyp=None):
        t = super().build_transforms(hyp)
        if self.augment:  # train split only; rebuilt with it when mosaic closes
            t.transforms.insert(-1, IRPhotometric())
        return t


class IRTrainer(DetectionTrainer):
    def build_dataset(self, img_path, mode="train", batch=None):
        ds = super().build_dataset(img_path, mode, batch)
        if mode == "train" and type(ds) is YOLODataset:
            # Same object, our subclass: adds IRPhotometric and keeps it when mosaic closes.
            ds.__class__ = IRDataset
            ds.transforms = ds.build_transforms(hyp=self.args)
        return ds

    def get_dataloader(self, dataset_path, batch_size=16, rank=0, mode="train"):
        """Ultralytics' loader always pins memory. On this Windows + CUDA 13 machine that crashed
        epoch 1 of the first run ('CUDA error: resource already mapped' in the pin-memory
        thread), so pinning is turned off. Single-GPU only (no DDP barrier)."""
        from ultralytics.data import build_dataloader

        dataset = self.build_dataset(dataset_path, mode, batch_size)
        return build_dataloader(
            dataset, batch=batch_size,
            workers=self.args.workers if mode == "train" else self.args.workers * 2,
            shuffle=mode == "train", rank=rank,
            drop_last=self.args.compile and mode == "train", device=self.device,
            pin_memory=False,
        )
