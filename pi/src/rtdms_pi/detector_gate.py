"""Pure detector gating based on user/profile settings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

T1 = TypeVar("T1")
T2 = TypeVar("T2")
T3 = TypeVar("T3")


def apply_settings(
    settings: Mapping[str, Any] | None,
    face: T1,
    phone: T2,
    physio: T3,
) -> tuple[T1 | None, T2 | None, T3 | None]:
    if not settings:
        return face, phone, physio

    detectors = settings.get("detectors")
    if not isinstance(detectors, Mapping):
        return face, phone, physio

    out_face: T1 | None = face
    out_phone: T2 | None = phone
    out_physio: T3 | None = physio

    if detectors.get("drowsiness") is False:
        out_face = None

    if detectors.get("distraction") is False or detectors.get("phone") is False:
        out_phone = None

    if detectors.get("physiology") is False:
        out_physio = None

    return out_face, out_phone, out_physio
