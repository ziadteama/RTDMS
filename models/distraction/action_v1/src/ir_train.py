"""IR step 2: train the drinking (cup) model for our IR camera — one change per run, kept only on
IR validation (untrimmed SynDD-val): recall may drop <= 1 event and FA/h (all non-drinking clips)
may not rise, versus the current best.

Base recipe = the kept iteration 6: fine-tune the clean nano, 0.5 CE + 0.5 T^2 KL to the clean s
teacher (T=2, 8 epochs), sampling balanced over dataset x class, train drivers only.
Switches (each its own run):
  --camsim    simulate our camera on every training crop (p=0.8): smaller driver / low resolution
              (down to 25 %), barrel lens distortion, blur, sensor noise, IR-like tone (gamma,
              contrast, vignetting). RGB-sourced crops (3MDAD, EBDD) get the same tone changes.
  --hardneg   add the phone-in-hand hard negatives from SynDD TRAIN drivers (ir_hardneg.py).
Phone veto (fusion) kept. Test (SynDD-test + DAD, untrimmed) scored only if kept, report only.

python ir_train.py <name> [--camsim] [--hardneg] [--base <dir of current best>]
"""

import argparse
import importlib
import json
import os
import random
from collections import Counter
from pathlib import Path

import cv2
import ir_eval as I
import numpy as np
import overnight_fusion as F
import torch
import torch.nn.functional as tf
from PIL import Image

DATA = F.CLEAN / "data/clean_binary"
HARD = F.OUT / "ir/hardneg"
T, EPOCHS, LR = 2.0, 8, 2e-4


class CamSim:
    """Our camera on a 128 px gray crop: 160-degree IR at the mirror -> small, soft, noisy,
    distorted driver; IR tone."""

    def __init__(self, p=0.8, seed=None):
        self.p, self.rng = p, random.Random(seed)

    def __call__(self, img):
        if self.rng.random() > self.p:
            return img
        r = self.rng
        a = np.asarray(img.convert("L"), np.float32)
        h, w = a.shape
        s = r.uniform(0.25, 0.8)  # smaller driver / lower resolution
        a = cv2.resize(cv2.resize(a, (max(8, int(w * s)), max(8, int(h * s))),
                                  interpolation=cv2.INTER_AREA), (w, h), interpolation=cv2.INTER_LINEAR)
        k = r.uniform(-0.25, 0.05)  # barrel distortion
        yy, xx = np.indices((h, w), np.float32)
        x, y = (xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)
        rr = x * x + y * y
        a = cv2.remap(a, ((x * (1 + k * rr)) * w / 2 + w / 2).astype(np.float32),
                      ((y * (1 + k * rr)) * h / 2 + h / 2).astype(np.float32),
                      cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        if r.random() < 0.5:
            a = cv2.GaussianBlur(a, (0, 0), r.uniform(0.3, 1.6))
        a = 255 * (np.clip(a, 0, 255) / 255) ** r.uniform(0.6, 1.6)  # IR tone
        a = (a - a.mean()) * r.uniform(0.7, 1.3) + a.mean() + r.uniform(-25, 25)
        if r.random() < 0.5:  # vignetting
            a *= 1 - r.uniform(0, 0.45) * rr / max(rr.max(), 1e-6)
        a += np.random.default_rng(r.randrange(1 << 30)).normal(0, r.uniform(0, 10), a.shape)
        a = np.clip(a, 0, 255).astype(np.uint8)
        lo, hi = np.percentile(a, (1, 99))  # same D9 stretch as runtime
        if hi - lo >= 8:
            a = np.clip((a.astype(np.float32) - lo) * 255 / (hi - lo), 0, 255).astype(np.uint8)
        return Image.fromarray(a)


def dataset(camsim, hardneg, hard_n=0):
    from torchvision import datasets, transforms

    aug = [transforms.Grayscale(1)]
    if camsim:
        aug.append(CamSim())
    aug += [transforms.Grayscale(3),
            transforms.RandomResizedCrop(128, scale=(0.75, 1.0), ratio=(0.9, 1.1)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=0.35, contrast=0.35),
            transforms.RandomApply([transforms.GaussianBlur(5, (0.1, 1.5))], p=0.3),
            transforms.ToTensor()]
    ds = datasets.ImageFolder(str(DATA / "train"), transforms.Compose(aug))
    if hardneg:
        extra = sorted((HARD / "train/empty_hand").glob("*.jpg"))
        if hard_n:
            extra = random.Random(28).sample(extra, min(hard_n, len(extra)))
        idx = ds.class_to_idx["empty_hand"]
        ds.samples += [(str(p), idx) for p in extra]
        ds.targets = [t for _, t in ds.samples]
    keys = [(Path(p).name.split("_", 1)[0] + ("_hard" if "phone" in Path(p).name else ""), c)
            for p, c in ds.samples]
    counts = Counter(keys)
    return ds, [1.0 / counts[k] for k in keys], dict(counts)


def logits(model, x):
    out = model(x)
    if isinstance(out, (tuple, list)):
        out = out[1] if len(out) > 1 else out[0]
    return out


def train(root, camsim, hardneg, hard_n=0):
    from torch.utils.data import DataLoader, WeightedRandomSampler
    from ultralytics import YOLO

    out_pt = root / "weights/best.pt"
    if out_pt.exists():
        return out_pt
    torch.manual_seed(28)
    random.seed(28)
    dev = "cuda"
    student_pt = F.CLEAN / "runs/nano/weights/best.pt"
    teacher = YOLO(str(F.CLEAN / "runs/control/weights/best.pt")).model.float().to(dev).eval()
    student = YOLO(str(student_pt)).model.float().to(dev)
    for p in student.parameters():
        p.requires_grad_(True)
    ds, weights, counts = dataset(camsim, hardneg, hard_n)
    F.log(f"IR train {root.name}: groups {counts}")
    dl = DataLoader(ds, batch_size=64, num_workers=0,  # AppControl blocks DLLs in child processes
                    sampler=WeightedRandomSampler(weights, len(weights), replacement=True))
    opt = torch.optim.AdamW(student.parameters(), lr=LR, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, EPOCHS * len(dl))
    for ep in range(EPOCHS):
        student.train()
        tot = 0.0
        for x, y in dl:
            x, y = x.to(dev), y.to(dev)
            with torch.no_grad():
                tl = logits(teacher, x)
            sl = logits(student, x)
            loss = 0.5 * tf.cross_entropy(sl, y) + 0.5 * T * T * tf.kl_div(
                tf.log_softmax(sl / T, 1), tf.softmax(tl / T, 1), reduction="batchmean")
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            tot += float(loss.detach()) * len(y)
        F.log(f"IR train {root.name}: epoch {ep + 1}/{EPOCHS} loss {tot / len(ds):.4f}")
    ckpt = torch.load(student_pt, map_location="cpu", weights_only=False)
    ckpt["model"] = student.cpu().half().eval()
    ckpt.pop("ema", None)
    out_pt.parent.mkdir(parents=True, exist_ok=True)
    torch.save(ckpt, out_pt)
    return out_pt


_POSE = None


def torch_pose_points(gray, lm):
    """Drop-in for held_wrist.pose_points with the PyTorch yolo26n-pose (ncnn is blocked by
    Windows Application Control on this PC since 2026-11-14 afternoon). Same driver choice:
    person box containing the face centre, else the best score."""
    global _POSE
    from ultralytics import YOLO

    if _POSE is None:
        _POSE = YOLO(str(F.HERE.parents[1] / "models/yolo26n-pose.pt"))
    r = _POSE(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), imgsz=320, verbose=False, device="cpu")[0]
    if r.keypoints is None or len(r.boxes) == 0:
        return np.zeros((17, 3))
    boxes, scores, kps = r.boxes.xyxy.numpy(), r.boxes.conf.numpy(), r.keypoints.data.numpy()
    idx = list(range(len(boxes)))
    if lm is not None:
        fx, fy = (lm[10] + lm[152]) / 2
        inside = [i for i in idx if boxes[i, 0] <= fx <= boxes[i, 2] and boxes[i, 1] <= fy <= boxes[i, 3]]
        idx = inside or idx
    return kps[max(idx, key=lambda i: scores[i])].astype(float)


def score_ir(b, measure, scenes_val, scenes_test, model, rows):
    val = F.apply(I.widen(scenes_val), rows, True, None)
    best = None
    for p, x, w in F.GRID:
        params = dict(p=p, x=x, window=w)
        m = measure.metric(b, val, "nano", model, params)
        obj = m["recall"][0] / m["recall"][1] - 0.02 * m["fa_per_h"]
        if best is None or obj > best[0]:
            best = (obj, params, m)
    _, params, vm = best
    res = dict(params=params, val=I.summarise(I.records_from_metric(vm), "drinking"))
    if scenes_test is not None:
        res["test"] = {}
        for ds, ss in scenes_test.items():
            tm = measure.metric(b, F.apply(I.widen(ss), rows, True, None), "nano", model, params)
            res["test"][ds] = I.summarise(I.records_from_metric(tm), "drinking")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--camsim", action="store_true")
    ap.add_argument("--hardneg", action="store_true")
    ap.add_argument("--hard-n", type=int, default=0, help="subsample the hard negatives")
    ap.add_argument("--base", default=str(F.OUT / "overnight/distill_rw"))
    ap.add_argument("--base-key", default="nano/fp32")
    a = ap.parse_args()
    os.chdir(F.HERE)
    root = F.OUT / "ir" / a.name
    root.mkdir(parents=True, exist_ok=True)
    pt = train(root, a.camsim, a.hardneg, a.hard_n)
    # Evaluated from the PyTorch weights: ncnn is blocked by Windows Application Control on this
    # PC since 2026-11-14 afternoon (not bypassed). NCNN/INT8 export moves to the Pi.
    b = importlib.import_module("phase_b")
    b.DrinkingRule = importlib.import_module("held_alerts").DrinkingRule
    measure = importlib.import_module("overnight_measure")
    b.ROOT = root
    b.W.pose_points = torch_pose_points  # ncnn blocked on this PC
    models = {"nano/pt": (str(pt), "cup_bottle")}
    settings = {"nano": (0.35, 1.25)}
    rows = {}
    rows.update(F.phone_rows("syndd", "val"))
    for ds in ("syndd", "dad"):
        rows.update(F.phone_rows(ds, "test"))
    val = []
    for i, job in enumerate(b.windows("val")):
        val.append(b.predict_job(job, models, settings))
        F.log(f"IR {a.name} val predictions {i + 1}/20")
    cand = score_ir(b, measure, val, None, "nano/pt", rows)
    base_root = Path(a.base)
    val_clips = {j["clip"] for j in b.windows("val")}
    base_val = [json.loads(p.read_text()) for p in (base_root / "predictions").glob("syndd_*.json")]
    base_val = [s for s in base_val if s["job"]["clip"] in val_clips]
    cur = score_ir(b, measure, base_val, None, a.base_key, rows)
    # User's rule (IR step 2.5): recall may drop by at most 1 event, FA/h may not rise.
    kept = (cand["val"]["caught"][0] >= cur["val"]["caught"][0] - 1
            and cand["val"]["fa_per_h"] <= cur["val"]["fa_per_h"] + 1e-9)
    F.log(f"IR {a.name} val {cand['params']} {cand['val']['caught']} {cand['val']['fa_per_h']}/h "
          f"{cand['val']['false_by_type']} vs current {cur['val']['caught']} {cur['val']['fa_per_h']}/h -> "
          f"{'KEPT' if kept else 'REVERTED'}")
    res = dict(name=a.name, camsim=a.camsim, hardneg=a.hardneg, base=str(base_root),
               candidate_val=cand, current_val=cur, kept=kept)
    if kept:
        test = {"syndd": [b.predict_job(j, models, settings) for j in b.windows("test")],
                "dad": [b.predict_job(j, models, settings) for j in b.other_jobs("dad")]}
        res["test_report_only"] = score_ir(b, measure, val, test, "nano/pt", rows)["test"]
        F.log(f"IR {a.name} TEST report-only: " + json.dumps(
            {k: (v["caught"], v["fa_per_h"]) for k, v in res["test_report_only"].items()}))
    (root / "results.json").write_text(json.dumps(res, indent=1))
    F.log(f"JOB ir_{a.name} DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        F.log(f"JOB ir FAILED: {type(e).__name__}: {e}")
        raise
