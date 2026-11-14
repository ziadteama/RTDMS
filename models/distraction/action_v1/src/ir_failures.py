"""IR report item 4: example frames (3 per case) for the remaining IR-test failures of the final
configuration — drinking (IR-4 + phone veto) misses and false alarms; eating (E-1 + E-2 + E-4)
misses and false alarms. Writes report_assets/ir_fail_<n>.jpg and _held_data/ir/failures.json.

python ir_failures.py
"""

import importlib
import json
from pathlib import Path

import cv2
import ir_eat_fusion as EF
import ir_eat_train as E
import ir_eval as I
import numpy as np
import overnight_fusion as F
import torch

ASSETS = F.HERE.parent / "report_assets"


def grab(src, t, dad=False):
    if dad:
        files = sorted(Path(src).glob("*.png"), key=lambda p: int(p.stem.split("_")[1]))
        i = min(len(files) - 1, int(round(t * 45)))
        return cv2.imread(str(files[i])) if files else None
    cap = cv2.VideoCapture(src)
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    cap.release()
    return img if ok else None


def sheet(n, frames, caption):
    tiles = []
    for img, label in frames:
        if img is None:
            continue
        img = cv2.resize(img, (360, int(360 * img.shape[0] / img.shape[1])))
        cv2.putText(img, label, (6, 20), 0, 0.5, (0, 255, 255), 1)
        tiles.append(img)
    if not tiles:
        return None
    h = max(t.shape[0] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 0, cv2.BORDER_CONSTANT) for t in tiles]
    img = np.hstack(tiles)
    cv2.putText(img, caption[:90], (6, h - 8), 0, 0.5, (0, 255, 0), 1)
    name = f"ir_fail_{n:02d}.jpg"
    cv2.imwrite(str(ASSETS / name), img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return name


def main():
    b = importlib.import_module("phase_b")
    b.DrinkingRule = importlib.import_module("held_alerts").DrinkingRule
    measure = importlib.import_module("overnight_measure")
    cases, n = [], 0
    # Drinking (IR-4 product).
    res = json.loads((F.OUT / "ir/camsim_light/results.json").read_text())
    params = res["candidate_val"]["params"]
    rows = {}
    for ds in ("syndd", "dad"):
        rows.update(F.phone_rows(ds, "test"))
    test_clips = {j["clip"] for j in b.windows("test")}
    preds = [json.loads(p.read_text()) for p in (F.OUT / "ir/camsim_light/predictions").glob("*.json")]
    test = [s for s in preds if (s["job"]["dataset"] == "syndd" and s["job"]["clip"] in test_clips)
            or s["job"]["dataset"] == "dad"]
    for s in F.apply(I.widen(test), rows, True, None):
        m = measure.metric(b, [s], "nano", "nano/pt", params)
        for c in m["clips"]:
            miss = c["cls"] == "drinking" and not c["onsets"]
            fa = c["cls"] != "drinking" and c["onsets"]
            if not (miss or fa):
                continue
            fr = [f for f in s["frames"] if c["s"] <= f["t"] <= c["e"]]
            top = sorted(fr, key=lambda f: -(f["probs"].get("nano|nano/pt") or 0))[:3]
            dad = s["job"]["dataset"] == "dad"
            src = s["job"]["src"]
            imgs = [(grab(src, f["t"], dad), f"t={f['t']:.1f} cup={f['probs'].get('nano|nano/pt')}") for f in top]
            n += 1
            kind = "drinking miss" if miss else f"drinking false alarm on {c['label']}"
            cases.append(dict(task="drinking", kind=kind, clip=c["clip"],
                              image=sheet(n, imgs, f"{kind} {c['clip']}")))
    # Eating (E-1 + E-2 + E-4, IR-3 backbone).
    fz = E.Featurizer()
    vids = E.load_split("test", fz)
    head = E.Head(1280)
    head.load_state_dict(torch.load(F.OUT / "ir/eat_head.pt"))
    head = head.to(E.DEV).eval()
    probs = [E.eat_probs(head, v, 1280) for v in vids]
    erows = F.phone_rows("syndd", "test")
    mask = [a | c for a, c in zip(EF.phone_mask(vids, erows), EF.drink_mask(vids, "test"), strict=True)]
    probs = EF.masked(vids, probs, mask)
    fus = json.loads((F.OUT / "ir/eat_head_fusion.json").read_text()) if (F.OUT / "ir/eat_head_fusion.json").exists() \
        else json.loads((F.OUT / "ir/eat_fusion.json").read_text())
    thr, m = fus["final_params"]
    src_of = {j["clip"]: j["src"] for j in b.windows("test")}
    for v, p in zip(vids, probs, strict=True):
        onsets, last = [], -1e9
        for i, t in enumerate(v["t"]):
            if i + 1 >= m and p[i - m + 1:i + 1].mean() > thr and t - last >= 30:
                onsets.append(t)
                last = t
        for c in v["intervals"]:
            s, e = c["s"] - 0.5, c["e"] + 0.5
            hit = [a for a in onsets if s <= a <= e]
            miss = c["label"] == "eating" and not hit
            fa = c["label"] != "eating" and hit
            if not (miss or fa):
                continue
            idx = [i for i, t in enumerate(v["t"]) if s <= t <= e]
            top = sorted(idx, key=lambda i: -p[i])[:3] if miss else [i for i in idx if v["t"][i] in hit][:1]
            if fa:
                k = top[0]
                top = [max(idx[0], k - 2), k, min(idx[-1], k + 2)]
            imgs = [(grab(src_of[v["clip"]], float(v["t"][i])), f"t={v['t'][i]:.1f} p_eat={p[i]:.2f}") for i in top]
            n += 1
            kind = "eating miss" if miss else f"eating false alarm on {c['label']}"
            cases.append(dict(task="eating", kind=kind, clip=c["clip"],
                              image=sheet(n, imgs, f"{kind} {c['clip']}")))
    (F.OUT / "ir/failures.json").write_text(json.dumps(cases, indent=1))
    for c in cases:
        print(c)


if __name__ == "__main__":
    main()
