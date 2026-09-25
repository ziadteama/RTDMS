"""Minimal risk fusion for RTDMS (stub)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AlertPattern(StrEnum):
    NONE = "none"
    SHORT_BEEP = "short_beep"
    REPEATED = "repeated"
    CONTINUOUS = "continuous"
    MAX = "max"


@dataclass(frozen=True, slots=True)
class FusionDecision:
    pattern: AlertPattern
    reasons: list[str]


def decide(
    *,
    face: dict[str, object] | None = None,
    phone: dict[str, object] | None = None,
    physiology: dict[str, object] | None = None,
) -> FusionDecision:
    """Map model reports → alert pattern. Thresholds are stubs until calibrated."""
    reasons: list[str] = []
    pattern = AlertPattern.NONE

    if phone:
        phone_score = phone.get("phone_score")
        sustained = float(phone.get("sustained_phone_ms") or 0.0)
        if isinstance(phone_score, (int, float)) and phone_score >= 0.55 and sustained >= 300:
            pattern = AlertPattern.CONTINUOUS
            reasons.append("phone sustained")

    if face:
        state = str(face.get("state") or "")
        if state == "drowsy":
            pattern = max_pattern(pattern, AlertPattern.REPEATED)
            reasons.append("face drowsy")
        elif state == "distracted" and pattern is AlertPattern.NONE:
            pattern = AlertPattern.SHORT_BEEP
            reasons.append("face distracted")

    if physiology:
        fatigue = physiology.get("fatigue_probability")
        if isinstance(fatigue, (int, float)) and fatigue >= 0.7:
            if pattern in (AlertPattern.REPEATED, AlertPattern.CONTINUOUS):
                pattern = AlertPattern.MAX
                reasons.append("physio confirms")
            elif pattern is AlertPattern.NONE:
                pattern = AlertPattern.SHORT_BEEP
                reasons.append("physio elevated")

    return FusionDecision(pattern=pattern, reasons=reasons)


_ORDER = [
    AlertPattern.NONE,
    AlertPattern.SHORT_BEEP,
    AlertPattern.REPEATED,
    AlertPattern.CONTINUOUS,
    AlertPattern.MAX,
]


def max_pattern(a: AlertPattern, b: AlertPattern) -> AlertPattern:
    return a if _ORDER.index(a) >= _ORDER.index(b) else b


def stub_demo() -> None:
    d = decide(
        face={"state": "distracted"},
        phone={"phone_score": 0.8, "sustained_phone_ms": 500},
        physiology={"fatigue_probability": 0.2},
    )
    print(d.pattern.value, d.reasons)


if __name__ == "__main__":
    stub_demo()
