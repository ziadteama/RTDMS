"""Paths shared by the experiment scripts: the package root (no hard-coded user folders) and the
data root (configs/data.yaml `root`, overridable with the RTDMS_DATA environment variable)."""
import os
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]  # models/distraction
EXP = Path(__file__).resolve().parent
DATA = Path(os.environ.get("RTDMS_DATA") or
            yaml.safe_load((REPO / "configs" / "data.yaml").read_text(encoding="utf8"))["root"])
PY = sys.executable
for p in (REPO / "src", REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
