"""Minimal risk fusion for RTDMS (stub)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .emergency import EmergencyStage, EmergencyStatus


class AlertPattern(StrEnum):
    NONE = "none"
    SHORT_BEEP = "short_beep"
    REPEATED = "repeated"
    CONTINUOUS = "continuous"
    MAX = "max"


@dataclass(frozen=True, slots=True)
class FusionDecision:
    pattern: AlertPattern
    reasons: list[str] = field(default_factory=list)
    emergency: str | None = None  # "unresponsive" once the emergency monitor fires


def decide(
    *,
    face: dict[str, object] | None = None,
    phone: dict[str, object] | None = None,
    physiology: dict[str, object] | None = None,
    emergency: EmergencyStatus | None = None,
    break_due: bool = False,
) -> FusionDecision:
    """Map model reports → alert pattern. Thresholds are stubs until calibrated."""
    reasons: list[str] = []
    pattern = AlertPattern.NONE

    if phone:
        # The IR pipeline (models/distraction hybrid) already debounces: `call` / `texting` are
        # booleans that are true only after a sustained detection, so they alert directly.
        for action in ("call", "texting"):
            if phone.get(action) is True:
                pattern = AlertPattern.CONTINUOUS
                reasons.append(f"phone {action}")
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

    # `physiology` is accepted but does not change alerts. Heart-rate fatigue scores were no
    # better than elapsed drive time on MPD-DF (Subsystems/Physiology Decision Log.md), so a
    # physiology-only beep or a "physio confirms" escalation would be a guess. Heart rate returns
    # only as a shadow-mode score and an emergency vital-sign check (physiology pivot plan).
    del physiology

    if break_due and pattern is AlertPattern.NONE:
        pattern = AlertPattern.SHORT_BEEP
        reasons.append("break reminder")

    flag = None
    if emergency is not None and emergency.stage is not EmergencyStage.NORMAL:
        pattern = AlertPattern.MAX
        reasons.insert(0, emergency.reason or "driver not responding")
        if emergency.stage is EmergencyStage.EMERGENCY:
            flag = "unresponsive"

    return FusionDecision(pattern=pattern, reasons=reasons, emergency=flag)


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
