"""Assemble what pi_held/ needs on the Pi (run on the dev PC, then scp the folder):

    models/held_cup_nano_ncnn_model/   FP32 NCNN of the chosen nano cup model
    held_params.json                   rule parameters + vetoes chosen on validation
    mouth_fit.json                     D26 pose-mouth fallback fit (SynDD-train only)
    calib/                             600 TRAIN-driver crops for INT8 calibration on the Pi

python prepare_pi_bundle.py <ncnn model dir> <params json>   -> _held_data/pi_bundle/
scp -r _held_data/pi_bundle/* khalifa@<pi>:~/RTDMS/models/distraction/action_v1/pi_held/
(models/ and calib/ are not in git: they are generated, and calib/ holds dataset faces.)
"""

import json
import random
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "_held_data"
dest = OUT / "pi_bundle"
model, params = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())
dest.mkdir(parents=True, exist_ok=True)
shutil.copytree(model, dest / "models/held_cup_nano_ncnn_model", dirs_exist_ok=True)
(dest / "held_params.json").write_text(json.dumps(params, indent=1))
shutil.copy(OUT / "geometry_v2/mouth_fit.json", dest / "mouth_fit.json")
crops = sorted((OUT / "overnight/clean/data/clean_binary/train").rglob("*.jpg"))
random.Random(0).shuffle(crops)
(dest / "calib").mkdir(exist_ok=True)
for p in crops[:600]:
    shutil.copy(p, dest / "calib" / p.name)
print(f"bundle in {dest}: model, params {params}, 600 calib crops")
