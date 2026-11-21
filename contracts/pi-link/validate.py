"""Validate every fixture against its schema and check BLE payload sizes.

    python3 -m pip install jsonschema && python3 contracts/pi-link/validate.py
"""
import json
import pathlib
import sys

import jsonschema

root = pathlib.Path(__file__).parent
MAX_NOTIFY_BYTES = 240  # MTU 247 minus 3 B ATT header, minus margin
NOTIFIED = {"alert", "status", "physio"}
bad = 0
for fx in sorted((root / "fixtures").glob("*.json")):
    schema = json.loads((root / "schemas" / f"{fx.stem}.schema.json").read_text())
    data = json.loads(fx.read_text())
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as e:
        print(f"FAIL {fx.name}: {e.message}")
        bad += 1
        continue
    size = len(json.dumps(data, separators=(",", ":")).encode())
    if fx.stem in NOTIFIED and size > MAX_NOTIFY_BYTES:
        print(f"FAIL {fx.name}: {size} B > {MAX_NOTIFY_BYTES} B notify budget")
        bad += 1
    else:
        print(f"ok   {fx.name} ({size} B)")
sys.exit(1 if bad else 0)
