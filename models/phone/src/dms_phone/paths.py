"""Resolve paths relative to the phone package root (`models/phone/`)."""

from __future__ import annotations

from pathlib import Path

# src/dms_phone/<this> → models/phone/
PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def resolve_under_package(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    cwd = Path.cwd() / p
    if cwd.is_file() or cwd.is_dir():
        return cwd
    return PACKAGE_ROOT / p
