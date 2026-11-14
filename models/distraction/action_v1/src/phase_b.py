"""Detached drinking-only campaign: train three subsets, export, tune, evaluate, benchmark.

All generated artifacts remain below _held_data/phaseB. Test pixels are transient arrays.
Food and its human-labelling files are never training inputs or modified.
"""

# ruff: noqa: E402
import csv
import hashlib
import importlib
import itertools
import json
import os
import random
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "_held_data/phaseB"
ROOT.mkdir(parents=True, exist_ok=True)
os.chdir(ROOT)  # Keep auxiliary Ultralytics downloads inside the ignored artifact tree.
os.environ["YOLO_CONFIG_DIR"] = str(ROOT / "ultralytics_config")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OPENCV_FFMPEG_THREADS", "1")

torch = importlib.import_module("torch")  # Load CUDA DLLs before OpenCV; keep this order explicit.

import cv2
import held_wrist as W
import numpy as np
import yaml
from build_held import RUN_NAME, read_source, square_cover
from held_alerts import DrinkingRule
from held_geometry import hand_geometry, pose_mouth

CLASSES = ["cup_bottle", "empty_hand"]
SUBSETS = {"tight": (0.0, 1.0), "loose": (0.35, 1.25), "tight_drv": (0.0, 1.0)}
TOOLS = Path("C:/Users/youss/rtdms-tools/ncnn")


def roc_auc_score(labels, probabilities):
    labels, probabilities = np.asarray(labels), np.asarray(probabilities)
    order = np.argsort(probabilities, kind="stable")
    ranks = np.empty(len(order), float)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and probabilities[order[end]] == probabilities[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2
        start = end
    positive = int(labels.sum())
    negative = len(labels) - positive
    return (ranks[labels == 1].sum() - positive * (positive + 1) / 2) / (positive * negative)


def accuracy_score(labels, predictions):
    return float(np.mean(np.asarray(labels) == np.asarray(predictions)))


def save(name, obj):
    p = ROOT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf8")
    return json.loads(p.read_text(encoding="utf8"))


def prepare(subset):
    with open(W.OUT / RUN_NAME / "manifest.csv", encoding="utf8") as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if r["target"] in CLASSES and (subset == "loose" or int(r["tight"]))
        ]
    rng, chosen = random.Random(28), []
    for cls in CLASSES:
        groups = defaultdict(list)
        for r in rows:
            if r["split"] == "train" and r["target"] == cls:
                groups[(r["dataset"], r["driver"])].append(r)
        capped = defaultdict(list)
        for (ds, _), group in sorted(groups.items()):
            capped[ds] += rng.sample(group, min(60 if subset == "tight_drv" else 100, len(group)))
        for ds, group in capped.items():
            other = sum(len(v) for key, v in capped.items() if key != ds)
            chosen += (
                group
                if subset == "tight_drv"
                else rng.sample(group, min(len(group), other or len(group)))
            )
    # Equal class totals after driver<=100 and dataset<=50%-when-possible caps.
    n = min(sum(r["target"] == c for r in chosen) for c in CLASSES)
    train = [r for cls in CLASSES for r in rng.sample([r for r in chosen if r["target"] == cls], n)]
    if subset == "tight_drv":
        train = chosen  # No dataset equalisation or negative downsampling.
    selected = train + [r for r in rows if r["split"] == "val"]
    folder = ROOT / "data" / subset
    for r in selected:
        src = W.OUT / r["path"]
        dest = folder / r["split"] / r["target"] / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            os.link(src, dest)
    report = save(
        f"{subset}/data.json",
        dict(
            before=dict(Counter(f"{r['split']}/{r['dataset']}/{r['target']}" for r in rows)),
            after=dict(Counter(f"{r['split']}/{r['dataset']}/{r['target']}" for r in selected)),
            max_per_driver_class=60 if subset == "tight_drv" else 100,
            dataset_cap="none"
            if subset == "tight_drv"
            else "no dataset exceeds other datasets combined",
            balancing="inverse-class-frequency weighted sampling"
            if subset == "tight_drv"
            else "downsampling",
            class_balanced_train=True,
            food_excluded=True,
            selected=selected,
        ),
    )
    W.log(f"Read {subset}/data.json: before={report['before']}; after={report['after']}")
    return folder, selected


from train_cls import AugTrainer


class BalancedDriverTrainer(AugTrainer):
    """Keep capped negative diversity; sample equal class mass with replacement."""

    def get_dataloader(self, dataset_path, batch_size=16, rank=0, mode="train"):
        if mode != "train":
            return super().get_dataloader(dataset_path, batch_size, rank, mode)
        from ultralytics.data.build import InfiniteDataLoader, seed_worker

        ds = self.build_dataset(dataset_path, mode)
        counts = Counter(sample[1] for sample in ds.samples)
        weights = [1.0 / counts[sample[1]] for sample in ds.samples]
        sampler = torch.utils.data.WeightedRandomSampler(
            weights, len(weights), replacement=True, generator=torch.Generator().manual_seed(28)
        )
        return InfiniteDataLoader(
            ds,
            batch_size=batch_size,
            sampler=sampler,
            num_workers=self.args.workers,
            pin_memory=False,
            collate_fn=getattr(ds, "collate_fn", None),
            worker_init_fn=seed_worker,
        )


def train(subset, folder):
    import train_cls
    from train_cls import AugTrainer
    from ultralytics import YOLO, settings

    train_cls.RUNS = ROOT / "runs"
    settings.update(
        {
            "weights_dir": str(ROOT / "weights"),
            "datasets_dir": str(ROOT / "data"),
            "runs_dir": str(ROOT / "runs"),
        }
    )
    weight = ROOT / "runs" / subset / "weights/best.pt"
    if weight.exists() and (ROOT / subset / "training_done.json").exists():
        W.log(f"Resume phaseB: completed weights exist for {subset}")
        return weight
    base = Path("C:/Users/youss/projects/RTDMS/models/distraction/models/yolo26n-cls.pt")
    local = ROOT / "yolo26n-cls.pt"
    if not local.exists():
        shutil.copy2(base, local)
    model = YOLO(str(local))

    def progress(trainer):
        W.log(
            f"Train {subset}: epoch {trainer.epoch + 1}/{trainer.epochs}; "
            f"metrics={getattr(trainer, 'metrics', {})}"
        )

    model.add_callback("on_fit_epoch_end", progress)
    W.log(f"Starting {subset} two-way yolo26n-cls 128 training, up to 40 epochs, patience 8")
    model.train(
        data=str(folder),
        trainer=BalancedDriverTrainer if subset == "tight_drv" else AugTrainer,
        imgsz=128,
        epochs=40,
        batch=128,
        patience=8,
        project=str(ROOT / "runs"),
        name=subset,
        exist_ok=True,
        workers=4,
        seed=0,
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
        amp=True,
    )
    save(f"{subset}/training_done.json", dict(completed=True, weight=str(weight)))
    return weight


class Classifier:
    def __init__(self, folder, cup="cup_bottle", threads=4):
        folder = Path(folder)
        self.pt = folder.suffix == ".pt"
        if self.pt:
            from ultralytics import YOLO

            torch.set_num_threads(threads)
            self.model = YOLO(str(folder)).model.cpu().float().eval()
            self.index = next(int(i) for i, name in self.model.names.items() if name == cup)
            self.size = 128
            return
        import ncnn

        self.nc = ncnn
        self.net = ncnn.Net()
        self.net.opt.num_threads = threads
        self.net.opt.use_vulkan_compute = False
        assert self.net.load_param(str(folder / "model.ncnn.param")) == 0
        assert self.net.load_model(str(folder / "model.ncnn.bin")) == 0
        meta = yaml.safe_load((folder / "metadata.yaml").read_text())
        names = meta["names"]
        self.index = next(int(i) for i, name in names.items() if name == cup)
        self.size = int(meta["imgsz"][0])
        self.input, self.output = self.net.input_names()[0], self.net.output_names()[0]

    def __call__(self, gray):
        x = cv2.resize(gray, (self.size, self.size), interpolation=cv2.INTER_AREA)
        x = np.ascontiguousarray(np.repeat((x.astype(np.float32) / 255)[None], 3, axis=0))
        if self.pt:
            with torch.inference_mode():
                out = self.model(torch.from_numpy(x[None]))
            out = out[0] if isinstance(out, tuple) else out
            return float(out[0, self.index])
        ex = self.net.create_extractor()
        ex.input(self.input, self.nc.Mat(x))
        return float(np.array(ex.extract(self.output)[1]).reshape(-1)[self.index])


def export(subset, weight, folder, rows):
    from ultralytics import YOLO

    fp = weight.parent / "best_ncnn_model"
    try:
        if not all(
            (fp / name).is_file()
            for name in ("model.ncnn.param", "model.ncnn.bin", "metadata.yaml")
        ):
            W.log(f"Exporting {subset} FP32 NCNN")
            fp = Path(YOLO(str(weight)).export(format="ncnn", imgsz=128, half=False))
        Classifier(fp)  # Validate completed export before using it.
        backend = "fp32"
    except Exception as exc:
        W.log(f"FP32 NCNN export unavailable for {subset}: {exc}; using PyTorch checkpoint")
        fp, backend = weight, "pytorch"
    # ncnn2table is known blocked: do not invoke it again or alter executables/policy.
    W.log("INT8: open (ncnn2table blocked by Application Control)")
    save(
        f"{subset}/export_status.json",
        dict(
            int8="open (ncnn2table blocked by Application Control)",
            backend=backend,
            model=str(fp),
            executable_or_policy_changes=False,
        ),
    )
    result = {}
    val = [r for r in rows if r["split"] == "val"]
    y = [int(r["target"] == "cup_bottle") for r in val]
    for name, path in ((backend, fp),):
        net = Classifier(path)
        probs = [net(cv2.imread(str(W.OUT / r["path"]), 0)) for r in val]
        result[name] = dict(
            auc=float(roc_auc_score(y, probs)),
            accuracy=float(accuracy_score(y, np.array(probs) > 0.5)),
            frames=len(y),
            model=str(path),
            probabilities=probs,
        )
    saved = save(f"{subset}/crop_val.json", result)
    W.log(
        f"Read {subset} crop validation: "
        + str({k: {q: v for q, v in s.items() if q != "probabilities"} for k, s in saved.items()})
    )
    return fp, saved


def windows(split):
    from rtdms_distraction.datasets import syndd

    groups = defaultdict(list)
    for seg in syndd(W.DATA / "public/syndd/A1"):
        if seg.label in W.extract.SYNDD_MAP:
            groups[str(seg.video)].append(seg)
    with open(W.DATA / "action_v1/data/v2/syndd.csv", encoding="utf8") as f:
        wanted = {r["clip"] for r in csv.DictReader(f) if r["split"] == split}
    output = []
    for src, segs in groups.items():
        intervals = []
        for i, s in enumerate(segs):
            cid = f"{Path(src).stem}_{i:03d}"
            if cid in wanted:
                intervals.append(
                    dict(
                        clip=cid,
                        cls=W.extract.SYNDD_MAP[s.label],
                        label=s.label,
                        s=s.start_s + 0.5,
                        e=s.end_s - 0.5,
                    )
                )
        if intervals:
            output.append(
                dict(
                    dataset="syndd",
                    driver=segs[0].driver,
                    src=src,
                    clip=Path(src).stem,
                    intervals=intervals,
                )
            )
    assert sum(len(x["intervals"]) for x in output) == len(wanted)
    return output


def other_jobs(ds):
    # Same release_v2 clip universe as evaluate_v2.py, including non-held actions.
    jobs = []
    root = W.DATA / "action_v1/runs/release_v2" / ds
    for p in sorted(root.glob("*.json")):
        j = json.loads(p.read_text(encoding="utf8"))
        clip = j["clip"]
        fr = j["frames"]
        if ds == "3mdad":
            subject, action = clip.split("_AC")
            a = int(action)
            src = str(W.DATA / "raw/3mdad/front/Day-RGB2/RGB2" / subject / f"AC{a}")
            cls, label = W.extract.MDAD_MAP[a], f"AC{a}"
            driver = f"3mdad_s{int(subject[1:])}"
        else:
            tester, label = clip.split("_", 1)
            src = str(W.DATA / "raw/dad/x/DAD" / tester / label / "front_IR")
            cls = "normal" if label.startswith("normal") else W.extract.DAD_MAP[label][0]
            driver = f"dad_{tester.lower()}"
        jobs.append(
            dict(
                dataset=ds,
                driver=driver,
                src=src,
                clip=clip,
                intervals=[dict(clip=clip, cls=cls, label=label, s=fr[0]["t"], e=fr[-1]["t"])],
            )
        )
    return jobs


def predict_job(job, models, settings):
    """Continuous cached timeline; pose updated every third sampled frame, held in between."""
    dest = ROOT / "predictions" / f"{job['dataset']}_{job['clip']}.json"
    if dest.exists():
        cached = json.loads(dest.read_text(encoding="utf8"))
        if cached.get("campaign_version") == "optional_int8_driver60":
            return cached
    ds = job["dataset"]
    kind, cache = W.load_cache(dict(job))
    pitch_cache = {}
    if ds == "syndd":
        p = W.DATA / "eval_cache/rich/fps10" / f"{job['clip']}.npz"
        with np.load(p) as z:
            pitch_cache = {
                round(float(t), 1): float(v) for t, v in zip(z["t"], z["pitch"], strict=True)
            }
        cap = cv2.VideoCapture(job["src"], cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
        width, fps = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        stream = ((t, dict(video=job["src"], frame=round(t * fps))) for t in sorted(cache))
        scale = width / 640
    else:
        # Retain all sampled frames, including the first .5s omitted by the Phase A builder.
        tmp = dict(job, segments=[[0, float("inf"), "normal", "normal"]])
        stream = ((t, source) for t, _, source in W.frames(tmp))
        scale = 1 if ds == "3mdad" else 224 / 640
    fit = json.loads((W.OUT / "geometry_v2/mouth_fit.json").read_text())
    base_pose = W.OUT / "geometry" / f"{ds}_{job['clip']}.json"
    known = {}
    if base_pose.exists():
        known = {round(r["t"], 3): r["kp"] for r in json.loads(base_pose.read_text())["records"]}
    nets = {name: Classifier(Path(path), cup) for name, (path, cup) in models.items()}
    caps, frames, last_mesh, held_kp = {}, [], None, np.zeros((17, 3))
    analyzer = None
    from rtdms_distraction.facemesh import FaceAnalyzer

    for i, (t, source) in enumerate(stream):
        entry = cache.get(round(t, 1 if ds == "syndd" else 3))
        lm = entry[1] * scale if entry is not None and entry[0] else None
        gray = None
        if i % 3 == 0:
            if ds == "syndd":
                held_kp = entry[2].copy()
                held_kp[:, :2] *= scale
            elif round(t, 3) in known:
                held_kp = np.asarray(known[round(t, 3)])
            else:
                gray = read_source(source, caps)
                view = cv2.resize(gray, (640, round(gray.shape[0] * 640 / gray.shape[1])))
                held_kp = W.pose_points(view, None if lm is None else lm / scale).copy()
                held_kp[:, :2] *= scale
        if lm is not None:
            mouth = (lm[13] + lm[14]) / 2
            fh = float(np.linalg.norm(lm[10] - lm[152]))
            last_mesh = (t, mouth, fh)
        elif last_mesh is not None and t - last_mesh[0] <= 1:
            _, mouth, fh = last_mesh
        else:
            predicted = pose_mouth(held_kp, fit)
            mouth, fh = predicted if predicted is not None else (None, None)
        pitch = pitch_cache.get(round(t, 1))
        if pitch is not None and not np.isfinite(pitch):
            pitch = None
        if ds != "syndd" and lm is not None and i % 3 == 0:
            # Release JSON has only seven landmarks; get full mesh solely for missing pitch.
            if gray is None:
                gray = read_source(source, caps)
            full = W.extract.faces()(gray, upscale=2 if ds == "dad" else 1)
            if full is not None:
                if analyzer is None:
                    h, w = gray.shape
                    analyzer = FaceAnalyzer(np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1.0]]))
                pp = analyzer.solve_pose(full)
                pitch = pp[0] if pp else None
        rec = dict(t=t, pitch=pitch, probs={}, near={})
        for setting, (h, k) in settings.items():
            geo = hand_geometry(held_kp, mouth, fh, h)
            near = geo["distance"] is not None and geo["distance"] <= k
            rec["near"][setting] = near
            if near:
                if gray is None:
                    gray = read_source(source, caps)
                crop, _ = square_cover(gray, geo["crop"])
                for name, net in nets.items():
                    if name.startswith(setting + "/") or name.startswith("old/"):
                        rec["probs"][setting + "|" + name] = net(crop)
        frames.append(rec)
        if i % 500 == 0:
            W.log(f"Predict {ds} {job['clip']}: {i} sampled frames; pose every third")
    for cap in caps.values():
        cap.release()
    data = dict(job=job, frames=frames, campaign_version="optional_int8_driver60")
    save(str(dest.relative_to(ROOT)), data)
    return data


def score(scenes, setting, model, params):
    clips = []
    baselines = defaultdict(lambda: deque(maxlen=300))
    for scene in scenes:
        rule = DrinkingRule(**params)
        rule.baseline = baselines[scene["job"]["driver"]]
        events = []
        start = None
        for r in scene["frames"]:
            active, onset = rule.update(
                r["t"], r["near"][setting], r["probs"].get(setting + "|" + model), r["pitch"]
            )
            if onset and start is None:
                start = r["t"]
            elif not active and start is not None:
                events.append((start, r["t"]))
                start = None
        if start is not None:
            events.append((start, scene["frames"][-1]["t"]))
        for c in scene["job"]["intervals"]:
            onsets = sum(c["s"] <= a <= c["e"] for a, _ in events)
            if not onsets and c["cls"] == "drinking":
                onsets = int(any(a < c["s"] <= b for a, b in events))
            clips.append(dict(c, dur=c["e"] - c["s"], onsets=onsets))
    positives = [c for c in clips if c["cls"] == "drinking"]
    normal = [c for c in clips if c["cls"] in ("normal", "hand_on_face")]
    wrong = [c for c in clips if c["cls"] != "drinking"]
    hours = sum(c["dur"] for c in normal) / 3600
    neg_hours = sum(c["dur"] for c in wrong) / 3600
    fa = sum(c["onsets"] for c in normal)
    recall = sum(c["onsets"] > 0 for c in positives) / len(positives) if positives else 0
    all_fa = sum(c["onsets"] for c in wrong) / neg_hours if neg_hours else 0
    return dict(
        drinking_recall=[sum(c["onsets"] > 0 for c in positives), len(positives)],
        fa_normal_hof=[fa, hours, fa / hours if hours else None],
        drinking_false_by_class=dict(
            Counter(
                {
                    label: sum(c["onsets"] for c in wrong if c["label"] == label)
                    for label in sorted({c["label"] for c in wrong})
                }
            )
        ),
        negative_false_per_h=all_fa,
        objective=recall - 0.02 * all_fa,
        clips=clips,
    )


def evaluation(models, auc, primary):
    W.log(
        "Starting gated SynDD-val predictions and threshold tuning; tests not opened for selection"
    )
    scenes = [predict_job(j, models, SUBSETS) for j in windows("val")]
    candidates = []
    for subset in SUBSETS:
        for p, x, window in itertools.product(
            (0.5, 0.6, 0.7, 0.8, 0.9, 0.95), (5, 10, 15), (0.3, 0.5, 1.0, 1.5)
        ):
            params = dict(p=p, x=x, window=window)
            metric = score(scenes, subset, primary[subset], params)
            candidates.append(dict(subset=subset, params=params, metrics=metric))
    bests = {
        s: max([c for c in candidates if c["subset"] == s], key=lambda c: c["metrics"]["objective"])
        for s in SUBSETS
    }
    chosen = max(bests.values(), key=lambda c: (c["metrics"]["objective"], auc[c["subset"]]))
    locked = save(
        "selection.json",
        dict(
            chosen=chosen,
            both=bests,
            criterion="D12 val objective, then val crop AUC",
            test_used=False,
            pose_every=3,
        ),
    )
    W.log(
        "Read locked SynDD-val selection.json: "
        + str(
            {
                s: dict(
                    params=c["params"],
                    recall=c["metrics"]["drinking_recall"],
                    fa=c["metrics"]["fa_normal_hof"],
                )
                for s, c in bests.items()
            }
        )
    )
    subset, params = chosen["subset"], chosen["params"]
    exported = ROOT / "held_cup_n128"
    exported.mkdir(exist_ok=True)
    source = Path(models[primary[subset]][0])
    if source.is_dir():
        for p in source.iterdir():
            if p.is_file():
                shutil.copy2(p, exported / p.name)
    else:
        shutil.copy2(source, exported / "held_cup_n128.pt")
    save("chosen_backend.json", dict(model=primary[subset], path=str(source)))
    results = {}
    for ds in ("syndd", "3mdad", "dad"):
        jobs = windows("test") if ds == "syndd" else other_jobs(ds)
        pred = [predict_job(j, models, {subset: SUBSETS[subset]}) for j in jobs]
        result = {
            name: score(pred, subset, name, params)
            for name in models
            if name.startswith(subset + "/") or name.startswith("old/")
        }
        results[ds] = result
        save("test_results.json", results)
        W.log(
            f"Read saved {ds} test results: "
            + str(
                {
                    n: dict(recall=m["drinking_recall"], FA=m["fa_normal_hof"])
                    for n, m in result.items()
                }
            )
        )
    baseline = json.loads((W.DATA / "action_v1/runs/eval_v2_det2.json").read_text())
    save("release_comparison.json", dict(new=results, release_v2_det2=baseline, selection=locked))
    primary = {ds: value[primary[subset]] for ds, value in results.items()}
    targets = dict(
        syndd_recall_15_of_18=primary["syndd"]["drinking_recall"][0] >= 15,
        syndd_fa_zero=primary["syndd"]["fa_normal_hof"][0] == 0,
        dad_fa_le_4_5=primary["dad"]["fa_normal_hof"][2] <= 4.5,
        mdad_fa_below_28_5=primary["3mdad"]["fa_normal_hof"][2] < 28.5,
        note="New drinking-only FA compared with full-hybrid reference FA; no runtime integration",
    )
    W.log("Read targets.json: " + json.dumps(save("targets.json", targets)))
    return subset, results


def benchmark(subset, results):
    from rtdms_distraction.config import PoseConfig
    from rtdms_distraction.pose import PoseEstimator

    pose = PoseEstimator(
        PoseConfig(weights=str(W.BASE.parent / "models/yolo26n_pose_320_ncnn_model"), num_threads=4)
    )
    chosen = json.loads((ROOT / "chosen_backend.json").read_text())
    net = Classifier(Path(chosen["path"]))
    files = sorted((W.DATA / "raw/3mdad/front/Day-RGB2/RGB2").glob("S3/AC1/*.jpg"))[:100]
    frames = [cv2.imread(str(p), 0) for p in files]
    pt, ct = [], []
    for i, g in enumerate(frames * 2):
        t = time.perf_counter()
        pose.detect(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR))
        elapsed = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        patch, _ = square_cover(g, dict(center=[g.shape[1] / 2, g.shape[0] / 3], side=200))
        net(patch)
        crop_elapsed = (time.perf_counter() - t) * 1000
        if i >= len(frames):
            pt.append(elapsed)
            ct.append(crop_elapsed)
    # Report worst-case gate rate 100%, and observed chosen-gate rate across cached test streams.
    gate = []
    for p in (ROOT / "predictions").glob("*.json"):
        d = json.loads(p.read_text())
        gate += [r["near"][subset] for r in d["frames"] if subset in r["near"]]
    rate = float(np.mean(gate))
    pc = float(np.mean(pt) / 3 + rate * np.mean(ct))
    ssh = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            "khalifa@192.168.100.181",
            "echo ok",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    report = dict(
        backend=chosen["model"],
        threads=4,
        pose_ms=float(np.mean(pt)),
        crop_ms=float(np.mean(ct)),
        gate_rate=rate,
        extra_pc_ms=pc,
        extra_pi_estimate_ms=2.1 * pc,
        worst_gate_pi_estimate_ms=2.1 * (np.mean(pt) / 3 + np.mean(ct)),
        pi_estimate_only=True,
        pi_reachable=ssh.returncode == 0,
        pi_status="open" if ssh.returncode else "reachable: concurrent target bench still required",
        ssh_output=ssh.stdout + ssh.stderr,
        target_ms=10,
    )
    saved = save("latency.json", report)
    W.log("Read latency.json: " + json.dumps(saved))
    if ssh.returncode == 0:
        # Read-only target inspection; no stream/config changes or model deployment in Phase B.
        check = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=5",
                "khalifa@192.168.100.181",
                "vcgencmd get_throttled; ps -eo args | grep stream.py",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        save(
            "pi_inspection.json",
            dict(
                output=check.stdout + check.stderr,
                concurrent_benchmark="open; no target changes made",
            ),
        )


def main():
    cv2.setNumThreads(1)
    W.log("Phase B torch/CUDA probe: " + str(torch.cuda.is_available()))
    W.log("Phase B chain starting: drinking only; food wholly excluded; labels untouched")
    protected = [W.OUT / "label_food.html", W.OUT / "food_labels.csv"]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected if p.exists()}
    models, auc, primary = {}, {}, {}
    for subset in SUBSETS:
        folder, rows = prepare(subset)
        weight = train(subset, folder)
        quant, metric = export(subset, weight, folder, rows)
        backend = next(iter(metric))
        primary[subset] = subset + "/" + backend
        models[primary[subset]] = (str(quant), "cup_bottle")
        auc[subset] = metric[backend]["auc"]
    old_root = Path("C:/Users/youss/projects/RTDMS/models/distraction/models")
    old = []
    for path in sorted(old_root.glob("mouth_cls_*")):
        meta = yaml.safe_load((path / "metadata.yaml").read_text())
        if "drink" in meta["names"].values():
            models["old/" + path.name] = (str(path), "drink")
            old.append(path.name)
    save(
        "old_model_mapping.json",
        dict(models=old, cup_probability="P(drink), food and none are not cup"),
    )
    subset, results = evaluation(models, auc, primary)
    benchmark(subset, results)
    changed = [
        p for p, sha in hashes.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha
    ]
    if changed:
        W.log(
            "Food labelling files changed externally while running; no campaign stage writes "
            "them and their labels were not read for training: " + str(changed)
        )
    save(
        "phaseB_complete.json",
        dict(
            completed=True,
            selected=subset,
            food_excluded=True,
            food_labelling_files_written=False,
            externally_changed_labelling_files=changed,
            tests_used_for_selection=False,
            runtime_wiring_changed=False,
            docs_review_pending=True,
        ),
    )
    W.log("Phase B chain complete; results ready for review, no hybrid/stream wiring changed")


if __name__ == "__main__":
    main()
