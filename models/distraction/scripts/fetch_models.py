#!/usr/bin/env python3
"""Download the small runtime assets that are not in git.

    python scripts/fetch_models.py           # hand_landmarker.task (~7.5 MB)

The face landmarker bundle is shared with models/face (../face/models/face_landmarker.task).
The detector is produced by scripts/export_ncnn.py in the training environment.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

MODELS = Path(__file__).resolve().parents[1] / "models"
ASSETS = {
    "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                            "hand_landmarker/float16/latest/hand_landmarker.task",
}


def main() -> int:
    MODELS.mkdir(exist_ok=True)
    for name, url in ASSETS.items():
        dest = MODELS / name
        if dest.is_file():
            print(f"have {dest}")
            continue
        print(f"downloading {name} ...")
        tmp = dest.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)
        print(f"   -> {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    face = MODELS.parent.parent / "face" / "models" / "face_landmarker.task"
    print(f"face landmarker: {'found' if face.is_file() else 'MISSING'} at {face}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
