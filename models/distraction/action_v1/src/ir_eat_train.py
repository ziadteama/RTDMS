"""IR step 3: eating from hand-at-mouth crop SEQUENCES — a small temporal head on the small cup
model's own features (no food-visible labels; the dataset's time-stamped action labels only).

Features: the product nano (iteration 6, .pt) — pooled backbone features (input of the final
Linear) + its cup probability, per near frame; zeros + near=0 when the hand is not at the mouth.
On the Pi the backbone already runs for the drinking check, so the only extra cost is the head.
Head: Linear(D+2 -> 64) + GRU(64) + Linear(4) over T = 7 samples (~2.1 s at ~3.3 fps); classes
eating / drinking / phone / other. Train = SynDD train drivers (+ phone sequences from the train
hard-negative crops); epoch picked on validation windows; the eating EVENT rule (threshold,
smoothing) picked on IR validation (untrimmed SynDD-val, FA over all non-eating clips); SynDD-test
scored once, report only.

python ir_eat_train.py
"""

import csv
import json
import time
from collections import Counter, defaultdict

import numpy as np
import overnight_fusion as F
import torch
import torch.nn as nn

EAT = F.OUT / "ir/eat"
HARD = F.OUT / "ir/hardneg"
MODEL_DIR = __import__("os").environ.get("EAT_MODEL", "hardneg1500")  # product cup model
MODEL_PT = F.OUT / f"ir/{MODEL_DIR}/weights/best.pt"
CLASSES = ["eating", "drinking", "phone", "other"]
PHONE = {"phone_right_ear", "phone_left_ear", "phone_in_hand"}
T = 7
import os
YAWN_W = float(os.environ.get("EAT_YAWN_W", "1"))
HEAD_OUT = os.environ.get("EAT_HEAD_OUT", "eat_head")
MIN_NEAR = 2  # the head only runs on windows with >= 2 hand-at-mouth samples
DEV = "cuda"


def cls_of(label):
    if label == "eating":
        return 0
    if label == "drinking":
        return 1
    if label in PHONE:
        return 2
    return 3


class Featurizer:
    def __init__(self):
        from ultralytics import YOLO

        self.m = YOLO(str(MODEL_PT)).model.float().to(DEV).eval()
        head = self.m.model[-1]
        self.cup = next(int(i) for i, n in self.m.names.items() if n == "cup_bottle")
        self.buf = {}
        head.linear.register_forward_hook(lambda mod, inp, out: self.buf.__setitem__("f", inp[0]))

    @torch.no_grad()
    def __call__(self, crops):
        feats, cups = [], []
        for i in range(0, len(crops), 256):
            x = torch.from_numpy(crops[i:i + 256]).float().div(255)[:, None].repeat(1, 3, 1, 1).to(DEV)
            out = self.m(x)
            p = out[0] if isinstance(out, (tuple, list)) else out
            feats.append(self.buf["f"].float().cpu())
            cups.append(p[:, self.cup].float().cpu())
        if not feats:
            return np.zeros((0, 1), np.float32), np.zeros(0, np.float32)
        return torch.cat(feats).numpy(), torch.cat(cups).numpy()


def load_split(split, fz):
    vids = []
    for p in sorted((EAT / split).glob("*.npz")):
        z = np.load(p, allow_pickle=False)
        feats, cups = fz(z["crops"])
        vids.append(dict(clip=str(z["clip"]), driver=str(z["driver"]), t=z["t"], near=z["near"],
                         cidx=z["crop_index"], feats=feats, cups=cups,
                         intervals=json.loads(str(z["intervals"]))))
    return vids


def steps(v, dim):
    x = np.zeros((len(v["t"]), dim + 2), np.float32)
    for i, c in enumerate(v["cidx"]):
        if c >= 0:
            x[i, :dim] = v["feats"][c]
            x[i, dim] = v["cups"][c]
            x[i, dim + 1] = 1.0
    return x


def label_at(intervals, t):
    for c in intervals:
        if c["s"] <= t <= c["e"]:
            return c["label"]
    return None


HARDW = []


def windows(vids, dim):
    xs, ys = [], []
    for v in vids:
        x = steps(v, dim)
        labs = [label_at(v["intervals"], t) for t in v["t"]]
        for i in range(T - 1, len(x)):
            ls = labs[i - T + 1:i + 1]
            if ls[0] is None or any(lab != ls[0] for lab in ls):
                continue
            if x[i - T + 1:i + 1, dim + 1].sum() < MIN_NEAR:  # head runs only with hand at mouth
                continue
            xs.append(x[i - T + 1:i + 1])
            ys.append(cls_of(ls[0]))
            HARDW.append(YAWN_W if ls[0] in ("neg_yawning", "neg_hand_on_head") else 1.0)
    return np.array(xs, np.float32), np.array(ys, np.int64)


def phone_windows(fz, dim, drivers):
    rows = [r for r in csv.DictReader(open(HARD / "manifest.csv", encoding="utf8"))
            if r["driver"] in drivers]
    groups = defaultdict(list)
    for r in rows:
        groups[(r["clip"], r["label"])].append(r)
    xs = []
    for rs in groups.values():
        rs.sort(key=lambda r: float(r["t"]))
        crops = np.stack([__import__("cv2").imread(str(HARD / r["path"]), 0) for r in rs])
        feats, cups = fz(crops)
        seq = np.zeros((len(rs), dim + 2), np.float32)
        seq[:, :dim], seq[:, dim], seq[:, dim + 1] = feats, cups, 1.0
        # Only near frames were kept; insert a non-near step where samples are > 0.5 s apart.
        full, last = [], None
        for r, s in zip(rs, seq, strict=True):
            t = float(r["t"])
            if last is not None and t - last > 0.5:
                full += [np.zeros(dim + 2, np.float32)] * min(3, int((t - last) * 3) - 1)
            full.append(s)
            last = t
        full = np.array(full)
        for i in range(T - 1, len(full)):
            xs.append(full[i - T + 1:i + 1])
    return np.array(xs, np.float32).reshape(-1, T, dim + 2)


class Head(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.inp = nn.Sequential(nn.Linear(dim + 2, 64), nn.ReLU())
        self.gru = nn.GRU(64, 64, batch_first=True)
        self.out = nn.Linear(64, len(CLASSES))

    def forward(self, x):
        h, _ = self.gru(self.inp(x))
        return self.out(h[:, -1])


def eat_probs(head, v, dim):
    x = steps(v, dim)
    if len(x) < T:
        return np.zeros(len(x))
    w = np.stack([x[i - T + 1:i + 1] for i in range(T - 1, len(x))])
    with torch.no_grad():
        p = torch.softmax(head(torch.from_numpy(w).to(DEV)), 1)[:, 0].cpu().numpy()
    p[w[:, :, -1].sum(1) < MIN_NEAR] = 0.0  # not run without the hand at the mouth
    return np.concatenate([np.zeros(T - 1), p])


def score(vids, probs, thr, m, untrimmed=True):
    """Eating alert: mean P(eating) over the last m samples > thr; 30 s refractory. Clip caught
    if an onset falls in its (untrimmed) window; FA = onsets in non-eating clips / their hours."""
    recs = []
    for v, p in zip(vids, probs, strict=True):
        onsets, last = [], -1e9
        for i, t in enumerate(v["t"]):
            if i + 1 >= m and p[i - m + 1:i + 1].mean() > thr and t - last >= 30:
                onsets.append(t)
                last = t
        for c in v["intervals"]:
            s, e = (c["s"] - 0.5, c["e"] + 0.5) if untrimmed else (c["s"], c["e"])
            recs.append(dict(clip=c["clip"], cls="eating" if c["label"] == "eating" else c["cls"],
                             label=c["label"], dur=e - s, onsets=sum(s <= a <= e for a in onsets)))
    import ir_eval

    return ir_eval.summarise(recs, "eating")


def main():
    t0 = time.time()
    fz = Featurizer()
    data = {s: load_split(s, fz) for s in ("train", "val", "test")}
    dim = next(v["feats"].shape[1] for v in data["train"] if len(v["feats"]))
    F.log(f"Eat head: features dim {dim}; videos {[len(v) for v in data.values()]}; "
          f"near frames {[sum(int(x['near'].sum()) for x in v) for v in data.values()]}")
    xtr, ytr = windows(data["train"], dim)
    sw = np.array(HARDW, np.float32)
    ph = phone_windows(fz, dim, {v["driver"] for v in data["train"]})
    xtr = np.concatenate([xtr, ph])
    ytr = np.concatenate([ytr, np.full(len(ph), 2)])
    sw = np.concatenate([sw, np.ones(len(ph), np.float32)])
    swt = torch.from_numpy(sw).to(DEV)
    xva, yva = windows(data["val"], dim)
    F.log(f"Eat head: train windows {dict(Counter(ytr.tolist()))} (phone from hard negatives "
          f"{len(ph)}), val windows {dict(Counter(yva.tolist()))}")
    torch.manual_seed(28)
    head = Head(dim).to(DEV)
    counts = np.bincount(ytr, minlength=4)
    wts = torch.tensor(len(ytr) / (4 * np.maximum(counts, 1)), dtype=torch.float32, device=DEV)
    opt = torch.optim.AdamW(head.parameters(), lr=1e-3, weight_decay=1e-3)
    xt, yt = torch.from_numpy(xtr).to(DEV), torch.from_numpy(ytr).to(DEV)
    xv, yv = torch.from_numpy(xva).to(DEV), torch.from_numpy(yva).to(DEV)
    best = None
    for ep in range(25):
        head.train()
        perm = torch.randperm(len(xt), device=DEV)
        for i in range(0, len(perm), 256):
            j = perm[i:i + 256]
            loss = (nn.functional.cross_entropy(head(xt[j]), yt[j], weight=wts, reduction="none")
                    * swt[j]).sum() / (wts[yt[j]] * swt[j]).sum()
            opt.zero_grad()
            loss.backward()
            opt.step()
        head.eval()
        with torch.no_grad():
            pv = head(xv).argmax(1)
        rec = [float(((pv == c) & (yv == c)).sum() / max(1, int((yv == c).sum()))) for c in range(4)]
        bal = float(np.mean(rec))
        if best is None or bal > best[0]:
            best = (bal, ep, {k: v.clone() for k, v in head.state_dict().items()}, rec)
    head.load_state_dict(best[2])
    head.eval()
    F.log(f"Eat head: best val epoch {best[1] + 1}, balanced window recall {best[0]:.3f}, "
          f"per class {dict(zip(CLASSES, np.round(best[3], 3)))}")
    probs = {s: [eat_probs(head, v, dim) for v in vids] for s, vids in data.items() if s != "train"}
    cand = None
    for thr in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95):
        for m in (1, 2, 3, 5):
            r = score(data["val"], probs["val"], thr, m)
            obj = r["caught"][0] / r["caught"][1] - 0.02 * r["fa_per_h"]
            if cand is None or obj > cand[0]:
                cand = (obj, thr, m, r)
    _, thr, m, rv = cand
    rt = score(data["test"], probs["test"], thr, m)
    x1 = torch.zeros(1, T, dim + 2)
    head_cpu = Head(dim)
    head_cpu.load_state_dict({k: v.cpu() for k, v in head.state_dict().items()})
    head_cpu.eval()
    torch.set_num_threads(4)
    with torch.no_grad():
        for _ in range(20):
            head_cpu(x1)
        ts = time.perf_counter()
        for _ in range(200):
            head_cpu(x1)
    ms = (time.perf_counter() - ts) / 200 * 1000
    drivers = {s: len({v["driver"] for v in d if any(c["label"] == "eating" for c in v["intervals"])})
               for s, d in data.items()}
    res = dict(classes=CLASSES, T=T, dim=dim, best_epoch=best[1] + 1, val_window_recall=[float(v) for v in best[3]],
               rule=dict(thr=thr, m=m, refractory_s=30), val=rv, test_report_only=rt,
               head_ms_per_run_pc_cpu_4threads=round(ms, 3),
               eating_drivers_per_split=drivers, dad="no eating clips in DAD",
               source="SynDD rear view (monochrome, daylight) only — not active IR",
               minutes=round((time.time() - t0) / 60, 1))
    torch.save(head_cpu.state_dict(), F.OUT / f"ir/{HEAD_OUT}.pt")
    (F.OUT / f"ir/{HEAD_OUT}_results.json").write_text(json.dumps(
        res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    F.log(f"Eat head: rule thr={thr} m={m}; IR val eating {rv['caught']} {rv['fa_per_h']}/h; "
          f"IR test (report only) {rt['caught']} {rt['fa_per_h']}/h {rt['false_by_type']}; head {ms:.3f} ms/run")
    F.log("JOB eat_head DONE")


if __name__ == "__main__":
    main()
