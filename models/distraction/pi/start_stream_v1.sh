#!/usr/bin/env bash
# IR phone / drink detector + drowsiness (PERCLOS) on the Pi camera, served on http://<pi>:8080.
# Extra arguments go to scripts/stream.py.
cd "$(dirname "$0")/distraction"
export PYTHONPATH="$PWD/src:$PWD/../face/src"
exec ../.venv/bin/python scripts/stream.py --profile pi --no-rectify --roi full --detect-every 2 \
    --drowsiness --no-texting "$@"
