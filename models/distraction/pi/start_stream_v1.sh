#!/usr/bin/env bash
# IR phone / drink detector + drowsiness (PERCLOS) on the Pi camera, served on http://<pi>:8080.
# Extra arguments go to scripts/stream.py.
# Runs from the git clone (models/distraction/pi/) or from the ~/rtdms copy layout (see README.md).
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$HERE/../scripts/stream.py" ]; then DIST="$HERE/.."; FACE="$HERE/../../face"
else DIST="$HERE/distraction"; FACE="$HERE/face"; fi
cd "$DIST"
export PYTHONPATH="$DIST/src:$FACE/src"
exec "${RTDMS_PYTHON:-$HOME/rtdms/.venv/bin/python}" scripts/stream.py --profile pi --no-rectify --roi full --detect-every 2 \
    --drowsiness --no-texting "$@"
