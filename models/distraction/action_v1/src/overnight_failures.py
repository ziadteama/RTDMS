"""Overnight M4: example frames (3 per case) for the remaining VALIDATION failures of the final
nano configuration — every missed drinking clip and every false alarm. Writes
report_assets/overnight_fail_<n>.jpg (small) and _held_data/overnight/failures.json.

python overnight_failures.py <predictions dir> <model key> <params json> [phone_veto 0/1]
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import overnight_fusion as F


def frame(job, t):
    if job["dataset"] == "syndd":
        cap = cv2.VideoCapture(job["src"])
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, img = cap.read()
        cap.release()
        return img if ok else None
    files = sorted(Path(job["src"]).glob("*.jpg"))
    return cv2.imread(str(files[min(len(files) - 1, round(t * 3))])) if files else None


def main():
    import importlib

    pred_dir, model, params = Path(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3])
    phone = len(sys.argv) > 4 and sys.argv[4] == "1"
    b = importlib.import_module("phase_b")
    b.DrinkingRule = importlib.import_module("held_alerts").DrinkingRule
    measure = importlib.import_module("overnight_measure")
    frozen = set(json.loads((F.OUT / "overnight/step0/split_freeze.json").read_text())
                 ["mdad_validation_drivers"])
    val_clips = {j["clip"] for j in b.windows("val")}
    scenes = [json.loads(p.read_text()) for p in pred_dir.glob("*.json")]
    val = [s for s in scenes if (s["job"]["dataset"] == "syndd" and s["job"]["clip"] in val_clips)
           or (s["job"]["dataset"] == "3mdad" and s["job"]["driver"] in frozen)]
    rows = {}
    rows.update(F.phone_rows("syndd", "val"))
    rows.update(F.phone_rows("3mdad", "train", frozen))
    val = F.apply(val, rows, phone, None)
    cases, n = [], 0
    for s in val:
        m = measure.metric(b, [s], "nano", model, params)
        key = "nano|" + model
        for c in m["clips"]:
            miss = c["cls"] == "drinking" and not c["onsets"]
            fa = c["cls"] != "drinking" and c["onsets"]
            if not (miss or fa):
                continue
            fr = [f for f in s["frames"] if c["s"] <= f["t"] <= c["e"]]
            scored = sorted(fr, key=lambda f: -(f["probs"].get(key) or 0))[:3] if fr else []
            tiles = []
            for f in scored:
                img = frame(s["job"], f["t"])
                if img is None:
                    continue
                img = cv2.resize(img, (360, int(360 * img.shape[0] / img.shape[1])))
                cv2.putText(img, f"t={f['t']:.1f} cup={f['probs'].get(key)}", (6, 20), 0, 0.5,
                            (0, 255, 255), 1)
                tiles.append(img)
            name = None
            if tiles:
                n += 1
                h = max(t.shape[0] for t in tiles)
                tiles = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 0, cv2.BORDER_CONSTANT)
                         for t in tiles]
                name = f"overnight_fail_{n:02d}.jpg"
                cv2.imwrite(str(F.HERE.parent / "report_assets" / name), np.hstack(tiles),
                            [cv2.IMWRITE_JPEG_QUALITY, 80])
            near = sum(f["near"]["nano"] for f in fr)
            high = sum((f["probs"].get(key) or 0) > params["p"] for f in fr)
            cause = ("missed: hand never at mouth" if miss and not near else
                     "missed: cup score below threshold" if miss and not high else
                     "missed: rule did not fire (window/sip/tilt)" if miss else
                     f"false alarm on {c['label']}")
            cases.append(dict(dataset=s["job"]["dataset"], clip=c["clip"], label=c["label"],
                              kind="miss" if miss else "false_alarm", cause=cause,
                              near_frames=near, high_cup_frames=high, frames=len(fr),
                              image=name))
    (F.OUT / "overnight/failures.json").write_text(json.dumps(cases, indent=1))
    for c in cases:
        print(c)


if __name__ == "__main__":
    main()
