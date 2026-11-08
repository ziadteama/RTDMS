"""Item 6: 5-fold cross-validation by driver over the 59 SynDD train + val drivers (the 10 test
drivers stay untouched). Per fold: train a fresh yolo26n (COCO weights, IR-only, 512 px, the
det_v2d recipe in one stage, fewer epochs) on merged_b minus the fold's SynDD drivers, then
score alerts on the fold's drivers with eval_simple (thresholds phone .40 drink .45 food .40).
python cv5.py build | train <k> | resume <k> | eval <k> | summary
   python cv5.py all   (finish / resume all 5 folds, score them, print the summary)"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = REPO
PY = PY
SRC = Path(f"{DATA}/det_v2/merged_b")
OUT = Path(f"{DATA}/det_v2/cv5")
RUNS = Path(f"{DATA}/runs")
EPOCHS = 8
DRV = re.compile(r"syndd_(\d{5})__")


def folds():
    split = json.load(open(REPO / "configs" / "syndd_split.json"))
    drivers = sorted(d for d, v in split.items() if v in ("train", "val"))
    rng = np.random.default_rng(0)
    rng.shuffle(drivers)
    return [sorted(drivers[k::5]) for k in range(5)]


def build():
    fs = folds()
    json.dump(fs, open(OUT.parent / "cv5_folds.json", "w"), indent=1)
    for k, fold in enumerate(fs):
        ids = {d.split("_")[-1] for d in fold}
        root = OUT / f"fold{k}"
        n = {"train": 0, "val": 0}
        for sp in ("train", "val"):
            for kind in ("images", "labels"):
                (root / kind / sp).mkdir(parents=True, exist_ok=True)
        for sp in ("train", "val"):
            for img in (SRC / "images" / sp).iterdir():
                m = DRV.search(img.name)
                dest = "val" if m and m.group(1) in ids else "train"
                if dest == "val" and "__gray" in img.name:
                    continue
                lab = SRC / "labels" / sp / (img.stem + ".txt")
                for s, d in ((img, root / "images" / dest / img.name),
                             (lab, root / "labels" / dest / lab.name)):
                    if s.is_file() and not d.exists():
                        os.link(s, d)
                n[dest] += 1
        (root / "data.yaml").write_text(
            f"path: {root}\ntrain: images/train\nval: images/val\n"
            "names:\n  0: phone\n  1: drink\n  2: food\n", encoding="utf8")
        print(k, len(fold), "drivers", n, flush=True)


def train(k):
    subprocess.run([PY, str(REPO / "scripts" / "train.py"), "--data", str(OUT / f"fold{k}" / "data.yaml"),
                    "--imgsz", "512", "--epochs", str(EPOCHS), "--batch", "32", "--workers", "4",
                    "--look", "ir", "--name", f"cv5_fold{k}", "--patience", "50"], check=True, cwd=REPO)


def resume(k):
    """Continue a stopped fold from its last saved epoch (runs/cv5_fold<k>/weights/last.pt)."""
    last = RUNS / f"cv5_fold{k}" / "weights" / "last.pt"
    if not last.is_file():
        return train(k)
    # same trainer as scripts/train.py --look ir, so the IR augmentation continues too
    code = ("import sys; sys.path.insert(0, 'src'); from ultralytics import YOLO; "
            "from rtdms_distraction.training import IRTrainer; IRTrainer.look = 'ir'; "
            f"YOLO(r'{last}').train(resume=True, trainer=IRTrainer)")
    subprocess.run([PY, "-c", code], check=True, cwd=REPO)


def all_folds():
    """Finish every fold (resume where a checkpoint exists), then score each one."""
    for k in range(5):
        res = RUNS / f"cv5_fold{k}" / "results.csv"
        done = res.is_file() and len(res.read_text().strip().splitlines()) - 1 >= EPOCHS
        if not done:
            resume(k)
        eval_fold(k)
    summary()


def eval_fold(k):
    fold = folds()[k]
    split_file = OUT / f"fold{k}_split.json"
    json.dump({d: "cvtest" for d in fold}, open(split_file, "w"))
    w = RUNS / f"cv5_fold{k}" / "weights" / "last.pt"
    subprocess.run([PY, str(REPO / "scripts" / "eval_simple.py"), "--split-file", str(split_file),
                    "--split", "cvtest", "--models", f"cv{k}={w}@512", "--out",
                    str(RUNS / "overnight" / f"cv5_eval_fold{k}"), "--workers", "6",
                    "--class-conf", "phone=0.40,drink=0.45,food=0.40"], check=True, cwd=REPO)


def summary():
    rows = {}
    for k in range(5):
        p = RUNS / "overnight" / f"cv5_eval_fold{k}"
        js = sorted(p.glob("*.json"))
        if not js:
            continue
        rows[k] = json.load(open(js[0]))
    print(json.dumps(rows, indent=1)[:3000])


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "build":
        build()
    elif cmd == "train":
        train(int(sys.argv[2]))
    elif cmd == "resume":
        resume(int(sys.argv[2]))
    elif cmd == "all":
        all_folds()
    elif cmd == "eval":
        eval_fold(int(sys.argv[2]))
    else:
        summary()
