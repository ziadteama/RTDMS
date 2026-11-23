"""Stateful fusion helpers; inference is diagnostic only and stays in memory."""

import logging
from pathlib import Path
from typing import TypedDict

from dms_fusion import FusionDecision
from dms_fusion.break_reminder import BreakReminder
from dms_fusion.emergency import EmergencyInputs, EmergencyMonitor, EmergencyStage, EmergencyStatus
from dms_fusion.policy import AlertPolicy, PolicyOutput
from dms_fusion.shadow import ShadowTracker
from dms_physiology.model import LogisticModel

from .sources import number
from .state import Snapshot


def calibrating(s: Snapshot) -> bool:
    f = s.face
    return bool(f and (f.calibration == "calibrating" or f.calibration_step is not None))

class SafetyInputs(TypedDict):
    emergency: EmergencyStatus
    break_due: bool


def load_shadow(path: Path) -> LogisticModel | None:
    try:
        model = LogisticModel.from_json_file(path)
        if set(model.feature_names) != {"hr_delta_bpm", "hr_trend_bpm_per_10min"}:
            raise ValueError("unexpected shadow features")
        return model
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        logging.getLogger(__name__).warning("Shadow model unavailable; shadow scoring disabled")
        return None


class Safety:
    def __init__(self, model_path: Path) -> None:
        self.monitor = EmergencyMonitor()
        self.reminder = BreakReminder()
        self.shadow = ShadowTracker()
        self.model = load_shadow(model_path)
        self.policy = AlertPolicy()

    def inputs(self, s: Snapshot) -> SafetyInputs:
        if calibrating(s):  # eyes shut on purpose: no emergency count may carry over
            self.monitor.reset()
            return {"emergency": EmergencyStatus(EmergencyStage.NORMAL), "break_due": False}
        present = bool(s.camera_ok and s.face and s.face.face)
        raw = s.physio.raw if s.physio else {}
        ack_age = number(raw.get("ack_age_s"))
        worn, quality = raw.get("worn"), raw.get("quality")
        status = self.monitor.update(s.t, EmergencyInputs(
            closure_ms=s.face.closure_ms if present and s.face else None,
            ack=ack_age is not None and ack_age <= 2.0,
            worn=worn if isinstance(worn, bool) else None,
            wrist_still_s=number(raw.get("wrist_still_s")),
            hr_bpm=number(raw.get("hr_bpm")),
            hr_quality=quality if isinstance(quality, str) else None,
        ))
        return {"emergency": status, "break_due": self.reminder.due(s.t, present)}

    def finish(self, raw: FusionDecision, s: Snapshot) -> PolicyOutput:
        """Per-frame decision -> stable alert episode (the only thing outputs may act on)."""
        out = self.policy.update(s.t, raw, calibrating=calibrating(s))
        self.observe(out.decision, s)
        return out

    def observe(self, decision: FusionDecision, s: Snapshot) -> None:
        raw = s.physio.raw if s.physio else {}
        delta = number(raw.get("hr_delta_bpm"))
        trend = number(raw.get("hr_trend_bpm_per_10min"))
        score = None
        if self.model and raw.get("quality") == "good" and delta is not None and trend is not None:
            score = self.model.probability({
                "hr_delta_bpm": delta, "hr_trend_bpm_per_10min": trend,
            })
        self.shadow.observe(decision.pattern, score)

    def diagnostics(self) -> dict[str, object]:
        c = self.shadow.counts
        return {
            "shadow_agree": c.agree,
            "shadow_disagree": c.disagree,
            "shadow_only": c.shadow_only,
        }
