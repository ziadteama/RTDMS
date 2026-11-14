"""Overnight S1.4 — distil the s control into the nano product (nano clearly behind s on
SynDD-val drinking: 10/15 vs 13/15).

Student = clean nano (fine-tuned), teacher = clean s; loss = 0.5 CE(label) + 0.5 T^2 KL(teacher
|| student) at T = 2, class-balanced sampling, same crops (train drivers only; frozen 3MDAD-val
drivers excluded, as in the clean run). Then: FP32 NCNN export, gated predictions on the two
validation sets, rule parameters re-picked on validation WITH the kept fusion vetoes, and the
S3.3 keep rule against the current best. Test is scored only if kept (report only).

python overnight_distill.py
"""

import importlib
import json
import os
import random
import shutil
from pathlib import Path

import numpy as np
import overnight_fusion as F
import torch
import torch.nn.functional as tf

ROOT = F.OUT / "overnight/distill"
ROOT.mkdir(parents=True, exist_ok=True)
DATA = F.CLEAN / "data/clean_binary"
T, EPOCHS, LR = 2.0, 8, 2e-4


def logits(model, x):
    out = model(x)
    if isinstance(out, (tuple, list)):
        out = out[1] if len(out) > 1 else out[0]
    return out


def loader(split, train):
    from torch.utils.data import DataLoader, WeightedRandomSampler
    from torchvision import datasets, transforms

    aug = [transforms.Grayscale(3)]
    if train:
        aug += [transforms.RandomResizedCrop(128, scale=(0.75, 1.0), ratio=(0.9, 1.1)),
                transforms.RandomHorizontalFlip(),
                transforms.ColorJitter(brightness=0.35, contrast=0.35),
                transforms.RandomApply([transforms.GaussianBlur(5, (0.1, 1.5))], p=0.3)]
    else:
        aug += [transforms.Resize((128, 128))]
    ds = datasets.ImageFolder(str(DATA / split), transforms.Compose(aug + [transforms.ToTensor()]))
    if not train:
        return ds, DataLoader(ds, batch_size=128, shuffle=False, num_workers=0)
    counts = np.bincount(ds.targets)
    weights = [1.0 / counts[c] for c in ds.targets]
    sampler = WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)
    return ds, DataLoader(ds, batch_size=64, sampler=sampler, num_workers=0)


def train():
    from ultralytics import YOLO

    out_pt = ROOT / "weights/best.pt"
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
    ds, dl = loader("train", True)
    names_s = student.names if isinstance(student.names, dict) else dict(enumerate(student.names))
    assert [names_s[i] for i in range(len(names_s))] == ds.classes, (names_s, ds.classes)
    opt = torch.optim.AdamW(student.parameters(), lr=LR, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, EPOCHS * len(dl))
    _, vdl = loader("val", False)
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
            tot += float(loss) * len(y)
        student.eval()
        correct = n = 0
        with torch.no_grad():
            for x, y in vdl:
                p = tf.softmax(logits(student, x.to(dev)), 1).argmax(1).cpu()
                correct += int((p == y).sum())
                n += len(y)
        F.log(f"Distill epoch {ep + 1}/{EPOCHS}: loss {tot / len(ds):.4f}, crop-val acc {correct / n:.4f}")
    ckpt = torch.load(student_pt, map_location="cpu", weights_only=False)
    ckpt["model"] = student.cpu().half().eval()
    ckpt.pop("ema", None)
    out_pt.parent.mkdir(parents=True, exist_ok=True)
    torch.save(ckpt, out_pt)
    return out_pt


def main():
    os.chdir(F.HERE)
    from ultralytics import YOLO

    pt = train()
    ncnn_dir = ROOT / "weights/best_ncnn_model"
    if not ncnn_dir.exists():
        exported = YOLO(str(pt)).export(format="ncnn", imgsz=128, half=False)
        if Path(exported) != ncnn_dir:
            shutil.move(exported, ncnn_dir)
    F.log(f"Distill: exported FP32 NCNN {ncnn_dir}")
    b = importlib.import_module("phase_b")
    b.DrinkingRule = importlib.import_module("held_alerts").DrinkingRule
    clean = importlib.import_module("overnight_clean")
    measure = importlib.import_module("overnight_measure")
    frozen = sorted(json.loads((F.OUT / "overnight/step0/split_freeze.json").read_text())
                    ["mdad_validation_drivers"])
    b.ROOT = ROOT
    b.W.load_cache = clean.cache_loader(b, b.W.load_cache, set(frozen))
    models = {"nano/fp32": (str(ncnn_dir), "cup_bottle")}
    settings = {"nano": (0.35, 1.25)}
    val = {"syndd": [], "3mdad": []}
    for ds, jobs in (("syndd", b.windows("val")), ("3mdad", clean.mdad_jobs(b, frozen))):
        for i, job in enumerate(jobs):
            val[ds].append(b.predict_job(job, models, settings))
            if i % 10 == 0:
                F.log(f"Distill val predictions {ds}: {i + 1}/{len(jobs)}")
    import time

    while not (F.ROOT / "results.json").exists():  # the fusion job may still be running
        time.sleep(30)
    fusion = json.loads((F.ROOT / "results.json").read_text())
    final = fusion["final"]
    rows = {}
    rows.update(F.phone_rows("syndd", "val"))
    rows.update(F.phone_rows("3mdad", "train", set(frozen)))
    veto_val = {ds: F.apply(ss, rows, final["phone_veto"], final["yawn_thr"])
                for ds, ss in val.items()}
    cand = F.choose(b, measure, veto_val, "nano/fp32")
    # Current best on the same validation scenes = the clean nano with the kept vetoes.
    scenes = {p.stem: json.loads(p.read_text()) for p in (F.CLEAN / "predictions").glob("*.json")}
    val_clips = {j["clip"] for j in b.windows("val")}
    cur_val = {"syndd": [s for s in scenes.values() if s["job"]["dataset"] == "syndd"
                         and s["job"]["clip"] in val_clips],
               "3mdad": [s for s in scenes.values() if s["job"]["dataset"] == "3mdad"
                         and s["job"]["driver"] in frozen]}
    model_clean = json.loads((F.CLEAN / "selection.json").read_text())["selections"]["nano"]["model"]
    cur = F.choose(b, measure, {ds: F.apply(ss, rows, final["phone_veto"], final["yawn_thr"])
                                for ds, ss in cur_val.items()}, model_clean)
    kept = F.keep(cur, cand)
    F.log(f"Distill val {cand['params']} {F.brief(cand)} vs current {F.brief(cur)} -> "
          f"{'KEPT' if kept else 'REVERTED'}")
    res = dict(val_candidate=F.brief(cand), params=cand["params"], val_current=F.brief(cur),
               kept=kept)
    if kept:
        trows = {}
        for ds in ("syndd", "3mdad", "dad"):
            trows.update(F.phone_rows(ds, "test"))
        tests = {"syndd": b.windows("test"),
                 "3mdad": [j for j in b.other_jobs("3mdad") if j["driver"] not in frozen],
                 "dad": b.other_jobs("dad")}
        res["test_report_only"] = {}
        for ds, jobs in tests.items():
            pred = [b.predict_job(j, models, settings) for j in jobs]
            m = measure.metric(b, F.apply(pred, trows, final["phone_veto"], final["yawn_thr"]),
                               "nano", "nano/fp32", cand["params"])
            res["test_report_only"][ds] = dict(recall=m["recall"], fa_per_h=round(m["fa_per_h"], 2),
                                               false_by_type={k: v["false_alerts"] for k, v in
                                                              m["false_by_type"].items()
                                                              if v["false_alerts"]})
            F.log(f"Distill TEST report-only {ds}: {m['recall']} {m['fa_per_h']:.2f} FA/h")
    (ROOT / "results.json").write_text(json.dumps(res, indent=1))
    F.log("JOB distill DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        F.log(f"JOB distill FAILED: {type(e).__name__}: {e}")
        raise
