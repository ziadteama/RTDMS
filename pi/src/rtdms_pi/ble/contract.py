"""The sole schema boundary; unknown object properties are ignored."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.protocols import Validator

CONTRACT_VERSION = 1


def contract_dir() -> Path:
    override = os.getenv("RTDMS_CONTRACT_DIR")
    candidates = ([Path(override)] if override else []) + [
        parent / "contracts/pi-link" for parent in Path(__file__).resolve().parents
    ]
    found = next((p for p in candidates if (p / "schemas").is_dir()), None)
    if found is None:  # one source of truth: the monorepo checkout, no vendored copy
        raise FileNotFoundError("contracts/pi-link not found; set RTDMS_CONTRACT_DIR")
    return found


@lru_cache(maxsize=1)
def _validators() -> dict[str, Validator]:
    return {
        p.name.removesuffix(".schema.json"): Draft202012Validator(json.loads(p.read_text()))
        for p in (contract_dir() / "schemas").glob("*.json")
    }


def _strip(obj: Any, schema: dict[str, Any]) -> Any:
    if isinstance(obj, dict):
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        return {
            k: _strip(v, props.get(k, extra if isinstance(extra, dict) else {}))
            for k, v in obj.items()
            if k in props or extra is not False
        }
    if isinstance(obj, list):
        return [_strip(v, schema.get("items", {})) for v in obj]
    return obj


def validate(name: str, obj: object) -> dict[str, Any] | None:
    try:
        json.dumps(obj, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        return None
    validator = _validators()[name]
    clean = _strip(obj, cast(dict[str, Any], validator.schema))
    if not isinstance(clean, dict) or not validator.is_valid(clean):
        return None
    return clean
