#!/usr/bin/env bash
# Offline install of the RTDMS distraction runtime on a Raspberry Pi 5 (Pi OS trixie, Python 3.13).
# Everything comes from ./wheels: no internet needed. numpy and picamera2 come from the system.
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv --system-site-packages .venv
.venv/bin/pip install --no-index --find-links wheels -q \
    opencv-python-headless pyyaml ncnn ai-edge-litert --no-deps
.venv/bin/pip install --no-index --find-links wheels -q \
    backports.strenum flatbuffers tqdm typing-extensions protobuf ml_dtypes --no-deps
.venv/bin/python - <<'PY'
import importlib
for m in ("numpy", "cv2", "yaml", "ncnn", "ai_edge_litert.interpreter", "picamera2"):
    mod = importlib.import_module(m)
    print(f"  {m:28s} {getattr(mod, '__version__', 'ok')}")
PY
echo "installed: $(du -sh .venv | cut -f1) venv"
