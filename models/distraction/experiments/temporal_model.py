"""Idea B: tiny causal temporal model (1D conv, ~3 s receptive field) on per-frame features from
the cached face landmarks + detector boxes (det_v2d @512). Trained on SynDD train drivers,
threshold chosen on val, test scored once. Compared with the hand-written simple rules.

python temporal_model.py
"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

import eval_simple as E  # noqa: E402
from rtdms_distraction import datasets as D  # noqa: E402
from rtdms_distraction.config import SmoothingConfig  # noqa: E402
from rtdms_distraction.smoothing import BehaviourSmoother  # noqa: E402

REPO = REPO
OUT = Path(f"{DATA}/runs/overnight")
W = Path(f"{DATA}/runs/det_v2d_ir_512/weights/best.pt")
st = W.stat()
KEY = hashlib.sha1(f"{W.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:10]
DETS = Path(f"{DATA}/eval_cache/dets/det_v2d_512_{KEY}/fps10")
FACES = Path(f"{DATA}/eval_cache/faces/fps10")
BEH = ["phone", "drinking", "eating"]
LAB = {"phone_right_ear": 0, "phone_left_ear": 0, "phone_in_hand": 0, "drinking": 1, "eating": 2}


def features(video: Path):
    fz = np.load(FACES / f"{video.stem}.npz")
    dets = np.load(DETS / f"{video.stem}.npy")
    t, ok, lm = fz["t"], fz["ok"], fz["lm"]
    by_t = {}
    for row in dets:
        by_t.setdefault(round(float(row[0]), 4), []).append(row)
    feats, last = [], None
    for i in range(len(t)):
        if ok[i]:
            last = lm[i]
        f = np.zeros(20, np.float32)
        f[0] = float(ok[i])
        if last is not None:
            fw = max(1.0, float(np.linalg.norm(last[234] - last[454])))
            c = last[[1, 152]].mean(0)
            f[1], f[2], f[3] = c[0] / 640, c[1] / 360, fw / 640
            f[4] = (last[1, 0] - (last[234, 0] + last[454, 0]) / 2) / fw  # yaw proxy
            f[5] = (last[1, 1] - (last[33, 1] + last[263, 1]) / 2) / fw  # pitch proxy
        rows = by_t.get(round(float(t[i]), 4), [])
        for k in range(3):
            rk = [r for r in rows if int(r[1]) == k]
            if not rk:
                continue
            best = max(rk, key=lambda r: r[2])
            f[6 + k] = best[2]  # best score anywhere
            if last is not None:
                bx, by = (best[3] + best[5]) / 2, (best[4] + best[6]) / 2
                near = [r for r in rk if np.hypot((r[3] + r[5]) / 2 - c[0],
                                                  (r[4] + r[6]) / 2 - c[1]) <= 1.6 * fw]
                f[9 + k] = max((r[2] for r in near), default=0.0)  # best score near the face
                if k == 0:
                    f[12], f[13] = (bx - c[0]) / fw, (by - c[1]) / fw
                    f[14] = (best[5] - best[3]) * (best[6] - best[4]) / fw ** 2
            f[15 + k] = len(rk) / 5.0
        feats.append(f)
    return t, np.array(feats)


def labels(segs, t):
    y = np.zeros((len(t), 3), np.float32)
    mask = np.zeros(len(t), np.float32)
    for s in segs:
        sel = (t >= s.start_s) & (t < s.end_s)
        if s.label in LAB:
            y[sel, LAB[s.label]] = 1.0
            mask[sel] = 1.0
        elif E.is_negative(s.label):
            mask[sel] = 1.0
    return y, mask


class Net(nn.Module):
    """Causal: each output only sees the past (left padding)."""

    def __init__(self, n_in=20, h=32):
        super().__init__()
        self.c1 = nn.Conv1d(n_in, h, 5)
        self.c2 = nn.Conv1d(h, h, 5, dilation=2)
        self.c3 = nn.Conv1d(h, h, 5, dilation=4)
        self.out = nn.Conv1d(h, 3, 1)

    def forward(self, x):  # x: (B, F, T)
        x = torch.relu(self.c1(nn.functional.pad(x, (4, 0))))
        x = torch.relu(self.c2(nn.functional.pad(x, (8, 0))))
        x = torch.relu(self.c3(nn.functional.pad(x, (16, 0))))
        return self.out(x)


def load(split_name, drivers=None):
    split = json.load(open(REPO / "configs" / "syndd_split.json"))
    segs = [s for s in D.syndd(f"{DATA}/public/syndd/A1") if split.get(s.driver) == split_name
            and (drivers is None or s.driver in drivers)]
    data = []
    for v in sorted({str(s.video) for s in segs}):
        vs = [s for s in segs if str(s.video) == v]
        if not (DETS / f"{Path(v).stem}.npy").is_file():
            continue
        t, x = features(Path(v))
        y, m = labels(vs, t)
        data.append((v, t, x, y, m))
    return segs, data


def events_from(prob_by_video, thr):
    ev = {}
    for v, (t, p) in prob_by_video.items():
        sm = [BehaviourSmoother(SmoothingConfig(window_s=w, on_ratio=0.6, off_ratio=0.3))
              for w in (1.0, 0.5, 0.5)]
        e = {b: [] for b in BEH}
        open_ = {}
        for i in range(len(t)):
            for k, b in enumerate(BEH):
                on = sm[k].update(float(t[i]), bool(p[i, k] >= thr[k]), float(p[i, k])).active
                if on and b not in open_:
                    open_[b] = float(t[i])
                elif not on and b in open_:
                    e[b].append((open_.pop(b), float(t[i])))
        for b, s in open_.items():
            e[b].append((s, float(t[-1])))
        ev[v] = e
    return ev


def predict(net, data, mu, sd):
    net.eval()
    out = {}
    with torch.no_grad():
        for v, t, x, _, _ in data:
            xx = torch.tensor(((x - mu) / sd).T[None], dtype=torch.float32)
            out[v] = (t, torch.sigmoid(net(xx))[0].T.numpy())
    return out


def main():
    train_drivers = set(open(OUT / "B_train_drivers.txt").read().strip().split(","))
    _, tr = load("train", train_drivers)
    val_segs, va = load("val")
    test_segs, te = load("test")
    print(f"train videos {len(tr)}, val {len(va)}, test {len(te)}", flush=True)
    allx = np.concatenate([x for *_, x, _, _ in [(a, b, c, d, e) for a, b, c, d, e in tr]])
    mu, sd = allx.mean(0), allx.std(0) + 1e-6
    torch.manual_seed(0)
    net = Net()
    opt = torch.optim.AdamW(net.parameters(), lr=3e-3, weight_decay=1e-3)
    pos = np.concatenate([y[m > 0] for *_, y, m in tr])
    pw = torch.tensor((1 - pos.mean(0)) / np.maximum(pos.mean(0), 1e-3), dtype=torch.float32)
    lossf = nn.BCEWithLogitsLoss(reduction="none", pos_weight=pw.clamp(max=20))
    rng = np.random.default_rng(0)
    for ep in range(40):
        net.train()
        tot = 0.0
        for i in rng.permutation(len(tr)):
            _, _, x, y, m = tr[i]
            # random 60 s window per video per step
            T = len(x)
            s0 = rng.integers(0, max(1, T - 600))
            xs, ys, ms = x[s0:s0 + 600], y[s0:s0 + 600], m[s0:s0 + 600]
            xx = torch.tensor(((xs - mu) / sd).T[None], dtype=torch.float32)
            logit = net(xx)[0].T
            loss = (lossf(logit, torch.tensor(ys)) * torch.tensor(ms)[:, None]).sum() / \
                max(1.0, ms.sum())
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item()
        if ep % 10 == 9:
            print(f"epoch {ep + 1} loss {tot / len(tr):.4f}", flush=True)
    pv, pt = predict(net, va, mu, sd), predict(net, te, mu, sd)
    results = {}
    grid = (0.8, 0.85, 0.9, 0.93, 0.95, 0.97, 0.98, 0.99)
    rows = {0: ["phone_right_ear", "phone_left_ear", "phone_in_hand"], 1: ["drinking"], 2: ["eating"]}
    thr = [0.9, 0.9, 0.9]
    for k in range(3):  # each behaviour's threshold on its own (its alerts do not depend on others)
        best = None
        for th in grid:
            t3 = [1.1, 1.1, 1.1]; t3[k] = th
            res = E.summarise(E.score(val_segs, events_from(pv, t3)), n_boot=100)
            rec = sum(res[r]["recall"] for r in rows[k]) / len(rows[k])
            fa = res[rows[k][0]]["fa_per_h"]
            results[f"val {E.ROWS[rows[k][0]]} thr {th}"] = {r: res[r] for r in rows[k]}
            print(f"val {['phone', 'drinking', 'eating'][k]} thr {th}: recall {rec:.2f} "
                  f"({', '.join(f'{r} {res[r][chr(114)+chr(101)+chr(99)+chr(97)+chr(108)+chr(108)]:.2f}' for r in rows[k])}) FA/h {fa:.1f}", flush=True)
            score = rec - 0.05 * fa
            if best is None or score > best[0]:
                best = (score, th)
        thr[k] = best[1]
    res = E.summarise(E.score(test_segs, events_from(pt, thr)))
    results[f"TEST thr {thr}"] = res
    print(f"TEST thr {thr}:")
    for r in E.ROWS:
        x = res[r]
        print(f"  {r:16s} recall {x['recall']:.2f} {[round(v, 2) for v in x['recall_range']]} FA/h {x['fa_per_h']:.1f} {[round(v, 1) for v in x['fa_per_h_range']]} TTA {x['tta_median_s']}", flush=True)
    th = thr
    json.dump(results, open(OUT / "B_temporal_model.json", "w"), indent=1)
    torch.save({"state": net.state_dict(), "mu": mu, "sd": sd, "thr": th}, OUT / "B_temporal_model.pt")


if __name__ == "__main__":
    main()
