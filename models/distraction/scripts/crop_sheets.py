#!/usr/bin/env python3
"""Label-check contact sheets for the crop datasets (build_crops.py output).

    python scripts/crop_sheets.py ear-phone     # ~3 phone crops per 3MDAD driver + the other ear
    python scripts/crop_sheets.py mouth-test    # test-driver mouth crops (drink + none, max 200)

ear-phone: one row per driver: 3 crops labelled phone, each next to the other ear of the same
  frame when that crop survived the none cap. CLIP scores P(phone at the ear) on up to 12 phone
  crops per driver; a median < 0.5 flags the driver (the 3MDAD mirroring would put the phone
  label on the empty ear); flagged rows get a red label.
mouth-test: numbered tiles + <name>.csv (number, file, label) so wrong labels can be named by
  number. Sheets go to <root>/runs/label_checks/.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
T = 112


def tile(path: Path, text: str, colour=(0, 255, 255)) -> np.ndarray:
    im = cv2.resize(cv2.imread(str(path)), (T, T))
    cv2.rectangle(im, (0, 0), (T - 1, 13), (0, 0, 0), -1)
    cv2.putText(im, text, (2, 10), cv2.FONT_HERSHEY_SIMPLEX, 0.33, colour, 1, cv2.LINE_AA)
    return im


def label(text: str, w: int, colour=(255, 255, 255)) -> np.ndarray:
    im = np.zeros((T, w, 3), np.uint8)
    cv2.putText(im, text, (4, T // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.42, colour, 1, cv2.LINE_AA)
    return im


class ClipPhone:
    PHONE = ["a person holding a phone to their ear", "a phone pressed against an ear"]
    OTHER = ["a person's ear and hair", "the side of a person's head", "a car window"]

    def __init__(self):
        import clip
        import torch

        self.torch = torch
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, self.prep = clip.load("ViT-L/14", device=self.dev)
        with torch.no_grad():
            t = self.model.encode_text(clip.tokenize(self.PHONE + self.OTHER).to(self.dev))
            self.text = (t / t.norm(dim=-1, keepdim=True)).float()

    def p(self, path: Path) -> float:
        from PIL import Image

        im = Image.open(path).convert("RGB")
        with self.torch.no_grad():
            e = self.model.encode_image(self.prep(im).unsqueeze(0).to(self.dev)).float()
            e = e / e.norm(dim=-1, keepdim=True)
            pr = (100 * e @ self.text.T).softmax(-1)[0]
        return float(pr[:len(self.PHONE)].sum())


def ear_phone(crops: Path, out: Path, per_driver: int) -> None:
    rows = list(csv.DictReader(open(crops / "ear" / "manifest.csv", encoding="utf8")))
    by_file = {r["file"].split("/")[-1]: r for r in rows}
    drivers = defaultdict(list)
    for r in rows:
        if r["label"] == "phone" and r["source"] == "3mdad":
            drivers[r["driver"]].append(r)
    clipm = ClipPhone()
    rng = random.Random(0)
    lines, report = [], []
    for d in sorted(drivers, key=lambda s: int(s.rsplit("s", 1)[-1])):
        scored = rng.sample(drivers[d], min(12, len(drivers[d])))
        med = float(np.median([clipm.p(crops / "ear" / r["file"]) for r in scored]))
        pick = scored[:per_driver]
        tiles = []
        for r in pick:
            fn = r["file"].split("/")[-1]
            other = fn[:-5] + ("L.jpg" if fn.endswith("_R.jpg") else "R.jpg")
            pp = crops / "ear" / r["file"]
            o = by_file.get(other)
            po = crops / "ear" / o["file"] if o else None
            a = clipm.p(pp)
            b = clipm.p(po) if po else float("nan")
            tiles.append(tile(pp, f"phone {r['action'][6:]} {a:.2f}", (0, 255, 0)))
            tiles.append(tile(po, f"none {b:.2f}") if po else np.zeros((T, T, 3), np.uint8))
            tiles.append(np.full((T, 6, 3), 255, np.uint8))
        flag = med < 0.5
        report.append((d, len(drivers[d]), round(med, 3), flag))
        tiles += [np.zeros((T, 2 * T + 6, 3), np.uint8)] * (per_driver - len(pick))
        lines.append(np.hstack([label(f"{d[6:]} {med:.2f}{' FLAG' if flag else ''}", 150,
                                      (0, 0, 255) if flag else (255, 255, 255))] + tiles))
    half = (len(lines) + 1) // 2  # two columns of drivers
    left, right = lines[:half], lines[half:]
    right += [np.zeros_like(lines[0])] * (len(left) - len(right))
    sheet = np.hstack([np.vstack(left), np.full((half * T, 10, 3), 128, np.uint8),
                       np.vstack(right)])
    p = out / "ear_phone_per_driver.jpg"
    cv2.imwrite(str(p), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    with open(out / "ear_phone_per_driver.csv", "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["driver", "phone_crops", "median_clip_p_phone", "flag"])
        w.writerows(report)
    flagged = [d for d, *_, fl in report if fl]
    print(f"{len(report)} drivers; flagged {len(flagged)}: {flagged} -> {p}")


def mouth_test(crops: Path, out: Path, cap: int) -> None:
    rows = list(csv.DictReader(open(crops / "mouth" / "manifest.csv", encoding="utf8")))
    test = [r for r in rows if r["split"] == "test" and r["source"] == "3mdad"
            and r["label"] in ("drink", "none")]
    drink = [r for r in test if r["label"] == "drink"]
    none = [r for r in test if r["label"] == "none"]
    rng = random.Random(0)
    n_drink = min(len(drink), cap // 2 if len(none) >= cap // 2 else cap - len(none))
    pick = rng.sample(drink, n_drink) + rng.sample(none, min(len(none), cap - n_drink))
    pick.sort(key=lambda r: (r["label"], r["file"]))
    tiles = [tile(crops / "mouth" / r["file"], f"{i} {r['label']}",
                  (0, 255, 0) if r["label"] == "drink" else (0, 255, 255))
             for i, r in enumerate(pick, 1)]
    cols = 16
    tiles += [np.zeros((T, T, 3), np.uint8)] * (-len(tiles) % cols)
    sheet = np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
    p = out / "mouth_test_drivers.jpg"
    cv2.imwrite(str(p), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    with open(out / "mouth_test_drivers.csv", "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["n", "file", "label", "driver", "action"])
        w.writerows([i, r["file"], r["label"], r["driver"], r["action"]]
                    for i, r in enumerate(pick, 1))
    print(f"test drivers {sorted({r['driver'] for r in test})}: {len(drink)} drink, "
          f"{len(none)} none; sheet has {n_drink} drink + {len(pick) - n_drink} none -> {p}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("sheet", choices=["ear-phone", "mouth-test"])
    p.add_argument("--per-driver", type=int, default=3)
    p.add_argument("--max", type=int, default=200)
    args = p.parse_args()
    root = Path(yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))["root"])
    out = root / "runs" / "label_checks"
    out.mkdir(parents=True, exist_ok=True)
    if args.sheet == "ear-phone":
        ear_phone(root / "crops", out, args.per_driver)
    else:
        mouth_test(root / "crops", out, args.max)
    return 0


if __name__ == "__main__":
    sys.exit(main())
