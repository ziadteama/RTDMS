"""merged_b + extra TRAIN frames (hardlinks) -> a new YOLO set; val / test stay merged_b's.
python extend_set.py <out name> <extra set dir> [<extra set dir> ...]"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import os
import sys
from pathlib import Path

BASE = Path(f"{DATA}/det_v2/merged_b")


def link(s: Path, d: Path):
    if s.is_file() and not d.exists():
        os.link(s, d)


def main(name, extras):
    out = BASE.parent / name
    for sp in ("train", "val", "test"):
        for kind in ("images", "labels"):
            (out / kind / sp).mkdir(parents=True, exist_ok=True)
            for f in (BASE / kind / sp).iterdir():
                link(f, out / kind / sp / f.name)
    added = 0
    for e in extras:
        e = Path(e)
        for img in (e / "images" / "train").glob("*.jpg"):
            link(img, out / "images" / "train" / img.name)
            link(e / "labels" / "train" / (img.stem + ".txt"), out / "labels" / "train" / (img.stem + ".txt"))
            added += 1
    (out / "data.yaml").write_text(f"path: {out}\ntrain: images/train\nval: images/val\ntest: images/test\n"
                                   "names:\n  0: phone\n  1: drink\n  2: food\n", encoding="utf8")
    print(name, "added", added, "train frames", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
