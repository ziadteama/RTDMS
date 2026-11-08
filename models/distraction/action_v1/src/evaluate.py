"""Step 7: evaluate the action classifier + phone-in-hand classifier + alert logic, side by side
with the current release model (det_v2d + simple rules), on SynDD-test, 3MDAD-test (15 subjects),
EBDD-test (akkas, jewel) and DAD front IR (Tester1/10/11).

Metrics
  frame: per-class accuracy (recall), confusion matrix (rows = truth).
  event: clip recall per alert class (>= 1 alert of that class inside the clip);
         false alerts per hour = alert onsets of ANY kind on normal + hand_on_face clips.
         Release: "phone" alert counts for both call and texting clips.

python evaluate.py <action weights> <phone weights> [tag=v1]
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from alerts import ALERTS, CLASSES, AlertLogic  # noqa: E402

A = Path("D:/rtdms-data/action_v1")
DATA = Path("D:/rtdms-data")
PRED = A / "runs" / "preds"
ASSETS = A / "report_assets"
EDGE = 0.5
MDAD_ACT = {1: "normal", 2: "hand_on_face", 3: "other", 4: "other", 5: "texting", 6: "texting",
            7: "call", 8: "call", 10: "other", 11: "other", 12: "hand_on_face", 13: "drinking",
            14: "drinking", 15: "other", 16: "other"}
REL_KEY = {"call": "phone", "texting": "phone", "drinking": "drinking", "eating": "eating"}


# ----------------------------------------------------------------------------- data
def rows(ds, split="test"):
    p = A / "data" / f"{ds}.csv"
    rs = list(csv.DictReader(open(p, encoding="utf8"))) if p.exists() else []
    return [r for r in rs if r["split"] == split]


def predict(weights, paths, names_out, imgsz, batch=256):
    from ultralytics import YOLO

    m = YOLO(str(weights), task="classify")
    out = np.zeros((len(paths), len(names_out)), np.float32)
    order = None
    for k in range(0, len(paths), batch):
        res = m.predict(paths[k:k + batch], imgsz=imgsz, verbose=False, batch=batch)
        if order is None:
            names = [m.names[i] for i in range(len(m.names))]
            order = [names.index(c) for c in names_out]
        for j, r in enumerate(res):
            out[k + j] = r.probs.data.cpu().numpy()[order]
    return out


def preds(tag, ds, split, act_w, phone_w, act_sz=224):
    f = PRED / f"{tag}_{ds}_{split}.npz"
    rs = rows(ds, split)
    if f.exists():
        z = np.load(f)
        if len(z["act"]) == len(rs):
            return rs, z["act"], z["ph"]
    PRED.mkdir(parents=True, exist_ok=True)
    d = A / "data"
    act = predict(act_w, [str(d / r["up"]) for r in rs], CLASSES, act_sz)
    if phone_w:
        pr = predict(phone_w, [str(d / r["ear_r"]) for r in rs], ["phone_in_hand"], 128)[:, 0]
        pl = predict(phone_w, [str(d / r["ear_l"]) for r in rs], ["phone_in_hand"], 128)[:, 0]
        ph = np.stack([pr, pl], 1)
    else:
        ph = np.zeros((len(rs), 2), np.float32)
    np.savez(f, act=act, ph=ph)
    return rs, act, ph


# ----------------------------------------------------------------------------- clip durations
def syndd_windows():
    """clip id -> (video stem, start, end) of the usable window (segment minus 0.5 s edges)."""
    sys.path.insert(0, str(Path(r"C:\Users\youss\projects\RTDMS\models\distraction\src")))
    from rtdms_distraction import datasets as D

    from extract import SYNDD_MAP
    out = {}
    by = defaultdict(list)
    for s in D.syndd(DATA / "public/syndd/A1"):
        if s.label in SYNDD_MAP:
            by[str(s.video)].append(s)
    for v, segs in by.items():
        for k, s in enumerate(segs):
            out[f"{Path(v).stem}_{k:03d}"] = (Path(v).stem, s.start_s + EDGE, s.end_s - EDGE)
    return out


# ----------------------------------------------------------------------------- our model
def run_clips(rs, act, ph, dur=None, **kw):
    by = defaultdict(list)
    for k, r in enumerate(rs):
        by[r["clip"]].append(k)
    out = []
    for clip, ks in by.items():
        ks.sort(key=lambda k: float(rs[k]["t"]))
        lg = AlertLogic(**kw)
        ons = Counter()
        for k in ks:
            _, o = lg.update(float(rs[k]["t"]), act[k], float(ph[k].max()),
                             float(rs[k]["lip"]))
            ons.update(o)
        ts = [float(rs[k]["t"]) for k in ks]
        r0 = rs[ks[0]]
        d = (dur or {}).get(clip) or (ts[-1] - ts[0] + 0.4)
        out.append({"clip": clip, "cls": r0["cls"], "side": r0["side"], "dur": d,
                    "onsets": dict(ons)})
    return out


def summarise(cl, key=None):
    """key: alert class -> onset key (release uses "phone" for call and texting)."""
    key = key or {a: a for a in ALERTS}
    res = {}
    for c in ALERTS:
        pos = [x for x in cl if x["cls"] == c]
        if pos:
            res[f"{c}_recall"] = [sum(x["onsets"].get(key[c], 0) > 0 for x in pos), len(pos)]
    for s in ("L", "R"):
        pos = [x for x in cl if x["cls"] == "call" and x["side"] == s]
        if pos:
            res[f"call_{s}_recall"] = [sum(x["onsets"].get(key["call"], 0) > 0 for x in pos),
                                       len(pos)]
    for name, grp, which in (("fa_normal_hof", ("normal", "hand_on_face"), None),
                             ("fa_hof_phone", ("hand_on_face",), {key["call"], key["texting"]}),
                             ("fa_other", ("other",), None)):
        g = [x for x in cl if x["cls"] in grp]
        h = sum(x["dur"] for x in g) / 3600
        n = sum(v for x in g for a, v in x["onsets"].items() if which is None or a in which)
        res[name] = [n, round(h, 3), round(n / h, 1) if h else None]
    return res


# ----------------------------------------------------------------------------- release model
def onsets_from_frames(frames, t_of):
    ons, on, hit = Counter(), {}, set()
    for k, r in enumerate(frames):
        for b, lv in r["levels"].items():
            a = lv == "alert"
            if a and not on.get(b):
                ons[b] += 1
            if a:
                hit.add(b)
            on[b] = a
    return ons, hit


def release_syndd(win, test_clips):
    sys.path.insert(0, r"C:\Users\youss\projects\RTDMS\models\distraction\experiments")
    sys.path.insert(0, r"C:\Users\youss\projects\RTDMS\models\distraction\scripts")
    import ear_rule

    ev, out = {}, []
    for clip, cls, side in test_clips:
        stem, s, e = win[clip]
        if stem not in ev:
            ev[stem] = ear_rule.replay(stem, 0.0, 0.0)
        ons = Counter()
        for b, ivs in ev[stem].items():
            for a, z in ivs:
                if s <= a <= e:
                    ons[b] += 1
                elif a < s <= z:  # alert already on when the clip starts: counts for recall only
                    ons[b + "_carry"] += 1
        for b in list(ons):
            if b.endswith("_carry"):
                base = b[:-6]
                if cls in ("call", "texting", "drinking", "eating") and not ons.get(base):
                    ons[base] = 1
                del ons[b]
        out.append({"clip": clip, "cls": cls, "side": side, "dur": e - s,
                    "onsets": {k: v for k, v in ons.items() if v}})
    return out


def release_3mdad(subjects):
    out = []
    for f in sorted((DATA / "runs/unseen_3mdad/clips").glob("*.json")):
        c = json.loads(f.read_text(encoding="utf8"))
        if c["subject"] not in subjects or c["action"] not in MDAD_ACT or not c["frames"]:
            continue
        ons, _ = onsets_from_frames(c["frames"], None)
        out.append({"clip": f.stem, "cls": MDAD_ACT[c["action"]],
                    "side": {7: "L", 8: "R"}.get(c["action"], ""),
                    "dur": len(c["frames"]) / 3.0, "onsets": dict(ons)})
    return out


def release_dad():
    from extract import DAD_MAP
    out = []
    for f in sorted((DATA / "runs/unseen_dad/clips").glob("*__front_IR.json")):
        c = json.loads(f.read_text(encoding="utf8"))
        if not c["frames"]:
            continue
        a = c["action"]
        cls, side = ("normal", "") if a.startswith("normal") else DAD_MAP[a]
        ons, _ = onsets_from_frames(c["frames"], None)
        ts = [r["t"] for r in c["frames"]]
        out.append({"clip": f"{c['tester']}_{a}", "cls": cls, "side": side,
                    "dur": ts[-1] - ts[0] + 4 / 45, "onsets": dict(ons)})
    return out


def release_ebdd():
    from extract import EBDD_MAP
    out = []
    for f in sorted((A / "runs/release_ebdd").glob("*.json")):
        c = json.loads(f.read_text(encoding="utf8"))
        key = next(k for k in EBDD_MAP if f.stem.endswith("_" + k))
        drv = f.stem[: -len(key) - 1].lower()
        fr = [r for r in c["frames"] if EDGE <= r["t"] <= c["frames"][-1]["t"] - EDGE]
        ons, _ = onsets_from_frames(fr, None)
        out.append({"clip": f"ebdd_{drv}_{key}", "cls": EBDD_MAP[key], "side": "",
                    "dur": fr[-1]["t"] - fr[0]["t"] + 0.1, "onsets": dict(ons)})
    return out


# ----------------------------------------------------------------------------- frame metrics
def confusion(rs, act):
    cm = np.zeros((len(CLASSES), len(CLASSES)), int)
    for r, p in zip(rs, act, strict=True):
        cm[CLASSES.index(r["cls"]), int(p.argmax())] += 1
    return cm


def plot_cm(cm, title, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    ramp = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
    cmap = LinearSegmentedColormap.from_list("blue", ramp)
    keep = [i for i in range(len(CLASSES)) if cm[i].sum()]
    m = cm[keep]
    norm = m / np.maximum(m.sum(1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(7.2, 0.55 * len(keep) + 1.6), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.imshow(norm, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for i in range(norm.shape[0]):
        for j in range(norm.shape[1]):
            v = norm[i, j]
            if m[i, j] == 0:
                continue
            ax.text(j, i, f"{100 * v:.0f}%\n{m[i, j]}", ha="center", va="center", fontsize=7,
                    color="#fcfcfb" if v > 0.5 else "#0b0b0b")
    ax.set_xticks(range(len(CLASSES)), CLASSES, rotation=30, ha="right", fontsize=8,
                  color="#52514e")
    ax.set_yticks(range(len(keep)), [CLASSES[i] for i in keep], fontsize=8, color="#52514e")
    ax.set_xlabel("predicted", fontsize=8, color="#52514e")
    ax.set_ylabel("true", fontsize=8, color="#52514e")
    ax.set_title(title, fontsize=10, color="#0b0b0b", loc="left")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(path, facecolor="#fcfcfb")
    plt.close(fig)


# ----------------------------------------------------------------------------- talk threshold
def tune(tag, act_w, phone_w):
    """Pick TALK_STD on SynDD-val: the largest call recall whose false alerts on normal +
    hand_on_face stay within 0.5 / h of the phone-only variant."""
    rs, act, ph = preds(tag, "syndd", "val", act_w, phone_w)
    win = syndd_windows()
    dur = {c: e - s for c, (_, s, e) in win.items()}
    base = summarise(run_clips(rs, act, ph, dur, use_talk=False))
    lips = np.array([float(r["lip"]) for r in rs])
    out = {"phone_only": base}
    best = (None, base["call_recall"][0])
    for th in (0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.06):
        s = summarise(run_clips(rs, act, ph, dur, talk_std=th))
        out[f"talk_{th}"] = s
        if s["fa_normal_hof"][2] <= (base["fa_normal_hof"][2] or 0) + 0.5 and \
                s["call_recall"][0] > best[1]:
            best = (th, s["call_recall"][0])
    out["chosen_talk_std"] = best[0]
    out["lip_pctl_5_50_95"] = [round(float(np.percentile(lips, p)), 4) for p in (5, 50, 95)]
    return best[0], out


# ----------------------------------------------------------------------------- main
def main():
    act_w, phone_w = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""
    tag = sys.argv[3] if len(sys.argv) > 3 else "v1"
    ASSETS.mkdir(parents=True, exist_ok=True)
    talk, tuning = tune(tag, act_w, phone_w)
    print("talk threshold", talk, flush=True)
    variants = {"classifier only": dict(use_phone=False, use_talk=False),
                "+ phone crop": dict(use_talk=False),
                "+ talking": dict(use_phone=False, talk_std=talk or 9),
                "+ phone OR talking (plan)": dict(talk_std=talk or 9)}
    if talk is None:
        variants["+ phone OR talking (plan)"] = dict(use_talk=False)
    win = syndd_windows()
    sp = json.load(open(A / "splits" / "3mdad.json"))
    rel = {"3mdad": release_3mdad(set(sp["test"])), "dad": release_dad(),
           "ebdd": release_ebdd()}
    result = {"tuning_syndd_val": tuning, "datasets": {}}
    for ds in ("syndd", "3mdad", "ebdd", "dad"):
        rs, act, ph = preds(tag, ds, "test", act_w, phone_w)
        if not rs:
            continue
        cm = confusion(rs, act)
        plot_cm(cm, f"{ds} test: frame confusion (row %, count)", ASSETS / f"cm_{tag}_{ds}.png")
        per = {CLASSES[i]: round(float(cm[i, i] / cm[i].sum()), 3) for i in range(len(CLASSES))
               if cm[i].sum()}
        if ds == "syndd":
            dur = {c: e - s for c, (_, s, e) in win.items()}
            clips_ = sorted({(r["clip"], r["cls"], r["side"]) for r in rs})
            rel[ds] = release_syndd(win, clips_)
        else:
            dur = {c["clip"]: c["dur"] for c in rel.get(ds, [])}
        ours = {n: summarise(run_clips(rs, act, ph, dur, **kw)) for n, kw in variants.items()}
        rel_clips = {c["clip"] for c in rel.get(ds, [])}
        # same clip set on both sides where the release has the clip
        ours_same = summarise([c for c in run_clips(rs, act, ph, dur, **variants[
            "+ phone OR talking (plan)"]) if c["clip"] in rel_clips]) if rel_clips else None
        result["datasets"][ds] = {
            "frames": len(rs), "frame_acc": round(float(np.trace(cm) / cm.sum()), 3),
            "per_class_frame_acc": per, "confusion": cm.tolist(), "ours": ours,
            "ours_on_release_clips": ours_same,
            "release": summarise(rel[ds], REL_KEY) if ds in rel else None,
            "phone_prob_by_class": {c: round(float(np.mean([ph[k].max() for k, r in enumerate(rs)
                                                            if r["cls"] == c])), 3)
                                    for c in CLASSES if any(r["cls"] == c for r in rs)}}
        print(ds, json.dumps(result["datasets"][ds]["ours"]["+ phone OR talking (plan)"]),
              flush=True)
        print("  release", json.dumps(result["datasets"][ds]["release"]), flush=True)
    (A / "runs" / f"eval_{tag}.json").write_text(json.dumps(result, indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
