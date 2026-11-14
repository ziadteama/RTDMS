"""Versioned held-object experiments; never writes original labels or deployed models.

Stages are supervised by run_held_v2.py. Local checkpoints only; no downloads.
"""

# ruff: noqa: E402
import argparse
import csv
import hashlib
import importlib
import json
import os
import random
import shutil
import time
from collections import Counter, defaultdict
from pathlib import Path

torch = importlib.import_module("torch")  # CUDA DLLs before OpenCV.
import numpy as np
import phase_b as B
from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "_held_data"
ROOT = OUT / "held_object_v2"
ROOT.mkdir(parents=True, exist_ok=True)
SOURCE = OUT / "crops_loose_h035_k125/manifest.csv"
PROMPTS = ["a hand holding food near the mouth", "an empty hand touching the face"]
OLD = OUT / "phaseB"


def log(message):
    B.W.log(message)


def save(name, obj):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf8")
    return obj


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(name, rows, fields=None):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]) if rows else fields or [])
        writer.writeheader()
        writer.writerows(rows)


def sheet(name, rows, all_pages=False):
    rng = random.Random(42)
    rows = list(rows)
    rng.shuffle(rows)
    if not all_pages:
        rows = rows[:48]
    for start in range(0, len(rows), 48):
        page = rows[start : start + 48]
        canvas = Image.new("RGB", (6 * 208, 8 * 238), "white")
        draw = ImageDraw.Draw(canvas)
        for i, r in enumerate(page):
            x, y = (i % 6) * 208, (i // 6) * 238
            im = Image.open(OUT / r["path"]).convert("RGB").resize((192, 192))
            canvas.paste(im, (x, y))
            draw.text((x, y + 193), str(r.get("driver_id", r.get("driver", "")))[:27], fill="black")
            draw.text((x, y + 209), str(r.get("new_label", r.get("target", "")))[:27], fill="black")
            draw.text((x, y + 222), str(r.get("confidence", ""))[:24], fill="black")
        dest = ROOT / "sheets" / f"{name}_{start // 48:02d}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(dest, quality=80)


def wait_old():
    while True:
        status = json.loads((OUT / "phaseB_job.json").read_text())
        if status["state"] == "done":
            if "JOB phaseB DONE" not in (OUT / "LIVE.log").read_text(encoding="utf8", errors="replace"):
                raise RuntimeError("Phase B status done without required success marker")
            return
        if status["state"] == "failed":
            raise RuntimeError("Prerequisite phaseB failed; no v2 GPU training started")
        log("v2 waiting for JOB phaseB DONE; original chain untouched")
        time.sleep(30)


def setup_campaign(name):
    B.ROOT = ROOT / name
    B.ROOT.mkdir(parents=True, exist_ok=True)
    os.chdir(B.ROOT)
    os.environ["YOLO_CONFIG_DIR"] = str(B.ROOT / "ultralytics_config")


class V2Aug:
    """Additional low-light exposure and wider apparent-scale changes after CropAug."""

    def __call__(self, im):
        g = np.asarray(im.convert("L"))
        if random.random() < 0.35:
            g = np.clip(g.astype(np.float32) * random.uniform(0.25, 0.75), 0, 255).astype(np.uint8)
        if random.random() < 0.4:
            scale = random.uniform(0.65, 1.25)
            mat = B.cv2.getRotationMatrix2D((g.shape[1] / 2, g.shape[0] / 2), 0, scale)
            g = B.cv2.warpAffine(
                g, mat, (g.shape[1], g.shape[0]), borderMode=B.cv2.BORDER_REPLICATE
            )
        return Image.fromarray(g).convert("RGB")


class V2Trainer(B.BalancedDriverTrainer):
    def build_dataset(self, img_path, mode="train", batch=None):
        ds = super().build_dataset(img_path, mode, batch)
        if mode == "train":
            import torchvision.transforms as T

            ds.torch_transforms = T.Compose([V2Aug(), ds.torch_transforms])
        return ds


def link_data(name, train, val):
    folder = ROOT / "data" / name
    for split, rows in (("train", train), ("val", val)):
        for r in rows:
            src = OUT / r["path"]
            dest = folder / split / r["target"] / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                os.link(src, dest)
    return folder


def fit(name, folder, base, epochs):
    from ultralytics import YOLO, settings

    if not base.is_file():
        raise FileNotFoundError(f"R1 missing local checkpoint: {base}")
    weight = ROOT / "runs" / name / "weights/best.pt"
    if (ROOT / f"{name}_trained.json").is_file() and weight.is_file():
        log(f"v2 resume trained {name}")
        return weight
    settings.update(
        {
            "weights_dir": str(ROOT / "weights"),
            "datasets_dir": str(ROOT / "data"),
            "runs_dir": str(ROOT / "runs"),
        }
    )
    local = ROOT / "weights" / base.name
    local.parent.mkdir(parents=True, exist_ok=True)
    if not local.exists():
        shutil.copy2(base, local)
    model = YOLO(str(local))
    model.add_callback(
        "on_fit_epoch_end",
        lambda t: log(
            f"v2 train {name}: epoch {t.epoch + 1}/{t.epochs}; {getattr(t, 'metrics', {})}"
        ),
    )
    log(
        f"v2 train {name} starting: max {epochs} epochs, all retained drivers/crops, balanced sampling"
    )
    model.train(
        data=str(folder),
        trainer=V2Trainer,
        imgsz=128,
        epochs=epochs,
        batch=64,
        patience=8,
        project=str(ROOT / "runs"),
        name=name,
        exist_ok=True,
        workers=4,
        seed=28,
        deterministic=False,
        fliplr=0.5,
        scale=0.2,
        erasing=0.4,
        auto_augment=None,
        hsv_h=0,
        hsv_s=0,
        hsv_v=0,
        cos_lr=True,
        lr0=0.001,
        optimizer="AdamW",
        warmup_epochs=1,
        cache=False,
        plots=True,
        amp=False,
    )  # Avoid AMP's automatic reference-model download.
    save(f"{name}_trained.json", dict(weight=str(weight), epochs=epochs, complete=True))
    return weight


def kmeans(x, k, seed=42):
    rng = np.random.default_rng(seed)
    centers = x[rng.choice(len(x), k, replace=False)].copy()
    for _ in range(80):
        assignment = np.argmax(x @ centers.T, axis=1)
        new = np.array(
            [
                x[assignment == j].mean(0) if np.any(assignment == j) else x[rng.integers(len(x))]
                for j in range(k)
            ]
        )
        new /= np.maximum(np.linalg.norm(new, axis=1, keepdims=True), 1e-8)
        if np.max(np.abs(new - centers)) < 1e-5:
            break
        centers = new
    return assignment, centers


def food_labels(rows):
    import clip

    checkpoint = Path.home() / ".cache/clip/ViT-L-14.pt"
    if not checkpoint.is_file():
        raise FileNotFoundError(f"R1 local CLIP checkpoint missing: {checkpoint}")
    food = [r for r in rows if r["target"] == "food"]
    if len(food) != 1161:
        raise RuntimeError(f"R1 expected 1161 food crops, found {len(food)}; clarify corpus")
    log(f"v2labels CLIP ViT-L/14 embedding {len(food)} original food crops; local checkpoint only")
    cache = ROOT / "food_embeddings.npz"
    if not cache.exists():
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model, preprocess = clip.load(str(checkpoint), device=device, jit=False)
        embs = []
        with torch.inference_mode():
            text = model.encode_text(clip.tokenize(PROMPTS).to(device)).float()
            text /= text.norm(dim=-1, keepdim=True)
            for start in range(0, len(food), 8):
                batch = torch.stack(
                    [
                        preprocess(Image.open(OUT / r["path"]).convert("RGB"))
                        for r in food[start : start + 8]
                    ]
                ).to(device)
                e = model.encode_image(batch).float()
                e /= e.norm(dim=-1, keepdim=True)
                embs.append(e.cpu().numpy())
                if start % 80 == 0:
                    log(f"v2labels CLIP: {min(start + 8, len(food))}/{len(food)} crops")
        embedding = np.concatenate(embs)
        np.savez_compressed(cache, embedding=embedding, text=text.cpu().numpy())
        del model
        torch.cuda.empty_cache()
    with np.load(cache) as z:
        embedding, text = z["embedding"], z["text"]
    scores = embedding @ text.T
    logits = 100 * scores
    probabilities = np.exp(logits - logits.max(1, keepdims=True))
    probabilities /= probabilities.sum(1, keepdims=True)
    # Keep all candidate partitions for actual visual inspection, not pretend inspection.
    candidates = {}
    distance = np.maximum(0, 1 - embedding @ embedding.T)
    for k in (2, 3, 4, 6, 8):
        assignment, centers = kmeans(embedding, k)
        silhouette = []
        for i in range(len(food)):
            own = assignment == assignment[i]
            own[i] = False
            a = distance[i, own].mean() if own.any() else 0
            other = [
                distance[i, assignment == j].mean()
                for j in range(k)
                if j != assignment[i] and np.any(assignment == j)
            ]
            b = min(other)
            silhouette.append((b - a) / max(a, b, 1e-8))
        candidates[k] = dict(
            silhouette=float(np.mean(silhouette)),
            sizes=Counter(map(int, assignment)),
            assignments=assignment.tolist(),
        )
        for j in range(k):
            sheet(
                f"cluster_k{k}_{j}",
                [
                    dict(r, confidence=float(probabilities[i].max()))
                    for i, r in enumerate(food)
                    if assignment[i] == j
                ],
            )
    # Numerical choice is explicitly provisional pending sheet inspection in the next turn.
    chosen = max(candidates, key=lambda k: candidates[k]["silhouette"])
    assignment = np.array(candidates[chosen]["assignments"])
    cluster_scores = {
        j: float(np.median(scores[assignment == j, 0] - scores[assignment == j, 1]))
        for j in range(chosen)
    }
    output = {}
    for i, r in enumerate(food):
        margin = float(scores[i, 0] - scores[i, 1])
        cluster_margin = cluster_scores[int(assignment[i])]
        confident = float(probabilities[i].max()) >= 0.6 and abs(margin) >= 0.015
        agree = (margin > 0) == (cluster_margin > 0) and abs(cluster_margin) >= 0.015
        label = (
            ("food_visible" if margin > 0 else "empty_hand") if confident and agree else "uncertain"
        )
        output[r["path"]] = dict(
            new_label=label,
            confidence=float(probabilities[i].max()),
            cluster=int(assignment[i]),
            margin=margin,
            cluster_margin=cluster_margin,
        )
    save(
        "clip_cluster_review.json",
        dict(
            prompts=PROMPTS,
            selected_k=chosen,
            selection="maximum cosine silhouette, PROVISIONAL: visual inspection still required",
            inspection_complete=False,
            candidates=candidates,
            confidence_rule="p>=.6, abs cosine margin>=.015, cluster median abs margin>=.015, signs agree",
            caveat="Cluster semantics use median prompt margin: correlated evidence, not independent human verification",
        ),
    )
    log(
        f"Read CLIP clustering: provisional k={chosen}, counts={Counter(v['new_label'] for v in output.values())}; visual cluster inspection OPEN"
    )
    return output


def oof(rows):
    wait_old()
    binary = [r for r in rows if r["split"] == "train" and r["target"] in B.CLASSES]
    drivers = sorted({r["driver"] for r in binary})
    random.Random(28).shuffle(drivers)
    fold = {d: i % 5 for i, d in enumerate(drivers)}
    setup_campaign("oof")
    predictions = []
    base = Path("C:/Users/youss/projects/RTDMS/models/distraction/models/yolo26n-cls.pt")
    for f in range(5):
        dest = ROOT / f"oof/fold{f}.csv"
        if dest.exists():
            predictions += read_csv(dest)
            continue
        train = [r for r in binary if fold[r["driver"]] != f]
        val = [r for r in binary if fold[r["driver"]] == f]
        assert not {r["driver"] for r in train} & {r["driver"] for r in val}
        folder = link_data(f"oof{f}", train, val)
        weight = fit(f"oof{f}", folder, base, 15)
        net = B.Classifier(weight)
        pred = []
        for i, r in enumerate(val):
            p = net(B.cv2.imread(str(OUT / r["path"]), 0))
            pred.append(
                dict(
                    path=r["path"],
                    dataset=r["dataset"],
                    driver=r["driver"],
                    target=r["target"],
                    fold=f,
                    cup_probability=p,
                    self_confidence=p if r["target"] == "cup_bottle" else 1 - p,
                )
            )
            if i % 500 == 0:
                log(f"v2labels OOF fold {f + 1}/5: {i}/{len(val)} predictions")
        write_csv(f"oof/fold{f}.csv", pred)
        predictions += pred
    thresholds = {
        c: float(np.mean([float(r["self_confidence"]) for r in predictions if r["target"] == c]))
        for c in B.CLASSES
    }
    suspects = []
    confident_joint = np.zeros((2, 2), dtype=int)
    for r in predictions:
        p = float(r["cup_probability"])
        confidences = [p, 1 - p]
        eligible = [i for i, c in enumerate(B.CLASSES) if confidences[i] >= thresholds[c]]
        given = B.CLASSES.index(r["target"])
        confident = max(eligible, key=lambda i: confidences[i]) if eligible else None
        if confident is not None:
            confident_joint[given, confident] += 1
        suspect = confident is not None and confident != given
        suspects.append(
            dict(r, self_confidence=float(r["self_confidence"]), confident_disagreement=suspect)
        )
    suspects.sort(key=lambda r: r["self_confidence"])
    write_csv("oof_predictions.csv", suspects)
    write_csv("suspects_top200.csv", suspects[:200])
    sheet("suspect", suspects[:200], all_pages=True)
    save(
        "confident_learning.json",
        dict(
            thresholds=thresholds,
            confident_joint=confident_joint.tolist(),
            samples=len(predictions),
            flagged=sum(r["confident_disagreement"] for r in suspects),
            method="NumPy thresholded confident joint; per-class mean self confidence; rank by self confidence",
            packages_installed=False,
            relabelled=0,
            folds=fold,
            caveat="Cleanlab-style diagnostic, not an exact reproduction of all cleanlab pruning/calibration algorithms",
        ),
    )
    log(
        f"Read OOF diagnostic: {len(predictions)} crops, thresholds={thresholds}, flagged={sum(r['confident_disagreement'] for r in suspects)}; no relabelling"
    )


def labels():
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    rows = read_csv(SOURCE)
    food = food_labels(rows)
    versioned = []
    for r in rows:
        f = food.get(r["path"])
        versioned.append(
            dict(
                path=r["path"],
                source_dataset=r["dataset"],
                driver_id=r["driver"],
                old_label=r["target"],
                new_label=f["new_label"] if f else r["target"],
                method="clip_zeroshot+cluster" if f else "original_clip_label_x_geometry",
                confidence=f["confidence"] if f else "",
                split=r["split"],
                tight=r["tight"],
                clip=r["clip"],
                t=r["t"],
                original_label=r["original_label"],
                cluster=f["cluster"] if f else "",
            )
        )
    write_csv("manifest.csv", versioned)
    counts = Counter(
        (r["source_dataset"], r["driver_id"], r["split"], r["old_label"], r["new_label"])
        for r in versioned
    )
    write_csv(
        "counts_per_driver.csv",
        [
            dict(
                source_dataset=k[0],
                driver_id=k[1],
                split=k[2],
                old_label=k[3],
                new_label=k[4],
                count=v,
            )
            for k, v in sorted(counts.items())
        ],
    )
    totals = Counter(
        (r["source_dataset"], r["split"], r["old_label"], r["new_label"]) for r in versioned
    )
    write_csv(
        "counts_per_dataset.csv",
        [
            dict(source_dataset=k[0], split=k[1], old_label=k[2], new_label=k[3], count=v)
            for k, v in sorted(totals.items())
        ],
    )
    for group in ("food_visible", "empty_hand", "uncertain"):
        sheet(
            f"food_{group}",
            [r for r in versioned if r["old_label"] == "food" and r["new_label"] == group],
            all_pages=group == "uncertain",
        )
    save(
        "labels_metadata.json",
        dict(
            original_manifest_sha256=source_hash,
            manifest_sha256=hashlib.sha256((ROOT / "manifest.csv").read_bytes()).hexdigest(),
            all_crops=len(rows),
            food_crops=len(food),
            cluster_visual_inspection="OPEN; provisional k in clip_cluster_review.json",
            food_labels_not_training_inputs=True,
        ),
    )
    oof(rows)
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == source_hash
    save(
        "labels_complete.json",
        dict(completed=True, visual_cluster_review_pending=True, originals_untouched=True),
    )


def classification_stats(y, p):
    cm = np.zeros((2, 2), int)
    for a, probability in zip(y, p, strict=True):
        cm[a, int(probability <= 0.5)] += 1
    metrics = {}
    for i, label in enumerate(B.CLASSES):
        precision = cm[i, i] / max(cm[:, i].sum(), 1)
        recall = cm[i, i] / max(cm[i].sum(), 1)
        metrics[label] = dict(
            precision=float(precision),
            recall=float(recall),
            f1=float(2 * precision * recall / max(precision + recall, 1e-12)),
            support=int(cm[i].sum()),
        )
    return dict(classes=B.CLASSES, confusion=cm.tolist(), metrics=metrics)


def train():
    wait_old()
    if not (ROOT / "labels_complete.json").exists():
        raise RuntimeError("R1 v2labels completion missing")
    rows = read_csv(SOURCE)
    binary = [r for r in rows if r["target"] in B.CLASSES]
    splits = {s: {r["driver"] for r in rows if r["split"] == s} for s in ("train", "val", "test")}
    # The crop corpus intentionally contains no test crops: verify full v2 split CSVs too.
    for dataset in ("syndd", "3mdad", "ebdd", "dad"):
        path = B.W.DATA / f"action_v1/data/v2/{dataset}.csv"
        if not path.exists():
            raise FileNotFoundError(f"R1 split CSV missing: {path}")
        rr = read_csv(path)
        key = "driver" if "driver" in rr[0] else "driver_id"
        if key not in rr[0]:
            raise RuntimeError(f"R1 driver column missing in {path}: {list(rr[0])}")
        groups = {s: {r[key] for r in rr if r["split"] == s} for s in ("train", "val", "test")}
        for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
            if groups[a] & groups[b]:
                raise RuntimeError(f"Driver leakage in {dataset}: {a}/{b}")
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        assert not splits[a] & splits[b]
    save(
        "split_verification.json",
        dict(
            driver_disjoint=True,
            crops={s: len(v) for s, v in splits.items()},
            full_split_csvs_verified=True,
        ),
    )
    setup_campaign("evaluation")
    B.SUBSETS = {"v2_n": (0.35, 1.25), "v2_s": (0.35, 1.25)}
    models, auc, primary = {}, {}, {}
    train_rows = [r for r in binary if r["split"] == "train"]
    val_rows = [r for r in binary if r["split"] == "val"]
    folder = link_data("binary_all", train_rows, val_rows)
    save(
        "training_data.json",
        dict(
            counts=dict(Counter(f"{r['split']}/{r['dataset']}/{r['target']}" for r in binary)),
            dropped=0,
            cap=None,
            dataset_equalisation=False,
            balance="inverse class frequency weighted replacement sampling",
            all_original_food_excluded=True,
            clip_empty_food_excluded=True,
            augmentation="CropAug defaults: lens p.4 k[-.1,.3], tilt p.5 +/-15deg, brightness/contrast p.8 contrast[.6,1.4] shift[-40,40], gamma p.3 [.6,1.6], blur p.3 Gaussian3/5/7 or motion5/7/9, noise p.3 sigma[3,15]; additional exposure p.35 gain[.25,.75], scale p.4 [.65,1.25], replicate borders",
        ),
    )
    checkpoints = {
        "v2_n": Path("C:/Users/youss/projects/RTDMS/models/distraction/models/yolo26n-cls.pt"),
        "v2_s": Path("D:/rtdms-data/action_v1/src/yolo26s-cls.pt"),
    }
    for name, base in checkpoints.items():
        weight = fit(name, folder, base, 40)
        exported, metric = B.export(name, weight, folder, binary)
        backend = next(iter(metric))
        primary[name] = f"{name}/{backend}"
        models[primary[name]] = (str(exported), "cup_bottle")
        auc[name] = metric[backend]["auc"]
    # Only count explicit human rows, never CLIP pseudo-labels.
    human = OUT / "food_labels.csv"
    verified = []
    if human.exists():
        latest = {r["path"]: r for r in read_csv(human)}
        valid_paths = {r["path"] for r in rows if r["target"] == "food"}
        verified = [r for path, r in latest.items() if path in valid_paths and r["label"] == "food"]
    human_drivers = {r["driver"] for r in verified}
    eligible = len(verified) >= 300 and len(human_drivers) >= 3
    save(
        "human_food_gate.json",
        dict(
            human_file_exists=human.exists(),
            food_visible=len(verified),
            drivers=len(human_drivers),
            eligible=eligible,
            status="OPEN: separate three-class implementation/review required"
            if eligible
            else "SKIPPED: need >=300 human food-visible crops from >=3 drivers",
        ),
    )
    legacy = Path("C:/Users/youss/projects/RTDMS/models/distraction/models")
    for p in sorted(legacy.glob("mouth_cls_*")):
        if p.is_dir() and (p / "metadata.yaml").exists():
            meta = B.yaml.safe_load((p / "metadata.yaml").read_text())
            if "drink" in meta["names"].values():
                models["old/" + p.name] = (str(p), "drink")
    # Record transient test crops via classifier callbacks, then associate with frame times.
    original_predict, original_classifier = B.predict_job, B.Classifier
    context, captured = {}, defaultdict(list)

    class RecordingClassifier(original_classifier):
        def __init__(self, path, cup="cup_bottle", threads=4):
            self.record_key = str(path)
            super().__init__(path, cup, threads)

        def __call__(self, gray):
            if context.get("test"):
                captured[self.record_key].append(gray.copy())
            return super().__call__(gray)

    B.Classifier = RecordingClassifier
    class_results, test_manifest = defaultdict(lambda: ([], [])), []
    label_mapping = {(r["dataset"], r["original_label"]): r["target"] for r in binary}

    def recording_predict(job, all_models, settings):
        # Reuse of old-label predictions is impossible: ROOT is versioned and separate.
        context["test"] = (ROOT / "evaluation/selection.json").exists()
        captured.clear()
        result = original_predict(job, all_models, settings)
        if context["test"]:
            setting = next(iter(settings))
            for name, (path, _) in all_models.items():
                if not name.startswith(setting + "/"):
                    continue
                images = iter(captured[str(path)])
                for i, frame in enumerate(result["frames"]):
                    prob = frame["probs"].get(setting + "|" + name)
                    if prob is None:
                        continue
                    image = next(images, None)
                    dest = ROOT / "eval_test" / job["dataset"] / f"{job['clip']}_{i:06d}.jpg"
                    if image is not None:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        B.cv2.imwrite(str(dest), image)
                    interval = next(
                        (c for c in job["intervals"] if c["s"] <= frame["t"] <= c["e"]), None
                    )
                    label = (
                        label_mapping.get((job["dataset"], interval["label"])) if interval else None
                    )
                    if label is not None:
                        y, ps = class_results[(job["dataset"], name)]
                        y.append(B.CLASSES.index(label))
                        ps.append(prob)
                    test_manifest.append(
                        dict(
                            path=str(dest.relative_to(ROOT)),
                            dataset=job["dataset"],
                            driver=job["driver"],
                            clip=job["clip"],
                            t=frame["t"],
                            label=label or "unmapped",
                            original_label=interval["label"] if interval else "outside_interval",
                            model=name,
                            cup_probability=prob,
                        )
                    )
        return result

    B.predict_job = recording_predict
    B.DrinkingRule = importlib.reload(importlib.import_module("held_alerts")).DrinkingRule
    log("v2 evaluation loaded current D34 cadence-aware DrinkingRule before val selection")
    selected, results = B.evaluation(models, auc, primary)
    B.Classifier = original_classifier
    B.benchmark(selected, results)
    write_csv("eval_test/manifest.csv", test_manifest)
    metrics = {
        f"{ds}/{name}": classification_stats(y, p) for (ds, name), (y, p) in class_results.items()
    }
    y_all, p_all = [], []
    for y, p in class_results.values():
        y_all += y
        p_all += p
    metrics["all_heldout"] = classification_stats(y_all, p_all)
    save("classification_metrics.json", metrics)
    report(results, selected, primary, metrics)
    save(
        "v2_complete.json",
        dict(
            completed=True,
            cluster_visual_review_pending=True,
            docs_review_pending=True,
            human_three_class_open=eligible,
            pi="BLOCKED: unreachable; no labelled Pi IR set; INT8 tool policy block",
        ),
    )


def report(results, selected, primary, metrics):
    old = json.loads((OLD / "test_results.json").read_text())
    old_selection = json.loads((OLD / "selection.json").read_text())["chosen"]["subset"]
    baseline_path = B.W.DATA / "action_v1/runs/eval_v2_det2.json"
    if not baseline_path.exists():
        raise FileNotFoundError(f"R1 release baseline missing: {baseline_path}")
    release = json.loads(baseline_path.read_text())["datasets"]
    sha = hashlib.sha256((ROOT / "manifest.csv").read_bytes()).hexdigest()
    lines = [
        "# Held-object drinking results",
        "",
        f"Date: {time.strftime('%Y-%m-%d')}; dataset held_object_v2; manifest SHA256 `{sha}`.",
        "",
        "FP32/available backend, no INT8 claim. New thresholds selected only on SynDD-val.",
        "",
        "| Dataset | OLD labels drinking / FA/h | Release detector drinking / full-hybrid FA/h | Live Pi | NEW drinking / FA/h |",
        "|---|---|---|---|---|",
    ]
    for ds in ("syndd", "3mdad", "dad"):
        before = old[ds][old_selection + "/fp32"]
        after = results[ds][primary[selected]]
        ref = release[ds]["release"]
        lines.append(
            f"| {ds} | {before['drinking_recall']} / {before['fa_normal_hof'][2]} | "
            f"{ref['drinking_recall']} / {ref['fa_normal_hof'][2]} | OFF, 0 alerts | "
            f"{after['drinking_recall']} / {after['fa_normal_hof'][2]} |"
        )
    lines += [
        "",
        "FA/h is normal+hand_on_face for this standalone drinking rule; release FA covers the full hybrid.",
        "",
        "## S3.1–S3.2 Crop classification (gated frames with original known binary labels)",
        "",
        "| Set/model | Class | Precision | Recall | F1 | Support | Confusion (cup,empty) |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, item in metrics.items():
        for cls, m in item["metrics"].items():
            lines.append(
                f"| {key} | {cls} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} | {m['support']} | {item['confusion']} |"
            )
    lines += [
        "",
        "## S3.3 Event counts",
        "",
        "| Dataset | True drinking clips | Missed clips | False alerts | Normal hours | FA/h |",
        "|---|---|---|---|---|---|",
    ]
    for ds, models in results.items():
        r = models[primary[selected]]
        n, d = r["drinking_recall"]
        fa, hours, rate = r["fa_normal_hof"]
        lines.append(f"| {ds} | {n}/{d} | {d - n} | {fa} | {hours} | {rate} |")
    lines += [
        "",
        "## S3.4 False-alert breakdown",
        "",
        "| Dataset | Original label | False drinking onsets |",
        "|---|---|---|",
    ]
    for ds, models in results.items():
        for label, count in models[primary[selected]]["drinking_false_by_class"].items():
            lines.append(f"| {ds} | {label} | {count} |")
    latency = json.loads((B.ROOT / "latency.json").read_text())
    lines += [
        "",
        "## S3.5 / S4.2 Could not do or verify",
        "",
        f"PC four-thread latency (FP32/available backend): `{json.dumps(latency)}`.",
        "Pi concurrent FPS/latency and wrist check BLOCKED: need reachable key-auth Pi with running phone+face pipeline and ~20 camera frames. Labelled Pi IR evaluation additionally needs a labelled Pi set. x2.1 values are estimates only.",
        "INT8 BLOCKED by Application Control on ncnn2table; need an authorized environment/toolchain. No policy or executable changes attempted.",
        "No explicit rubbing-eyes action label found in the supplied action maps; need independently identified labelled clips. No silent substitution.",
        "Forehead mapping: SynDD neg_hand_on_head; 3MDAD AC2 hair/makeup is an imperfect proxy, reported as AC2. AC12 fatigue is not silently called rubbing eyes.",
        "CLIP k selection is numerical and provisional until candidate contact sheets are inspected. Pseudo-food labels never entered binary training. Uncertain stays unresolved.",
        "Classification excludes unmapped original action labels rather than guessing ground truth; all actions remain in event evaluation and eval_test manifest.",
        "Three-class gate and before/after counts are in versioned JSON/CSVs. Models and generated images remain ignored. Final documentation/visual review remains pending.",
    ]
    (BASE / "results.md").write_text("\n".join(lines) + "\n", encoding="utf8")
    doc = BASE / "HELD_OBJECT.md"
    with open(doc, "a", encoding="utf8") as f:
        f.write(
            f"\n\n## {time.strftime('%Y-%m-%d')} v2 campaign (review pending)\n\n"
            f"Dataset held_object_v2, manifest SHA256 `{sha}`. See [results.md](results.md). "
            "Phase A retained 22,612 of 39,465 eligible crops; 12,399 tight; food 1,161. "
            "Cup tight sheet review ~46/48 usable, food only ~7/48 visible; original food excluded. "
            "Original audit NCNN wrist agreement mean .104 face heights, 91.7% within .25. "
            "D26 mouth fallback raised DAD drinking gate from 34 to 260/664 at h=0/K=1. "
            "Pi wrist/performance remain blocked. This automated entry requires final review.\n"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("labels", "train"))
    args = parser.parse_args()
    B.cv2.setNumThreads(1)
    (labels if args.stage == "labels" else train)()
