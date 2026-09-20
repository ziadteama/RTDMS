"""Resolve paths relative to the face package root (`models/face/`)."""

from __future__ import annotations

from pathlib import Path

# src/dms_face/<this file> → models/face/
PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def resolve_under_package(path: str | Path) -> Path:
    """Return an absolute path; relative paths are resolved from PACKAGE_ROOT."""
    p = Path(path)
    if p.is_absolute():
        return p
    cwd_candidate = Path.cwd() / p
    if cwd_candidate.is_file() or cwd_candidate.is_dir():
        return cwd_candidate
    return PACKAGE_ROOT / p
