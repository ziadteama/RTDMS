"""Alert policy: turns per-frame fusion decisions into stable alert episodes for every output.

decide() answers "what does this frame say?". Outputs (buzzer, phone voice, watch vibration) need
"what alert is active?": one alert at a time, raised at once, held until its cause has been gone
for a while, not restarted right after it ended, and silent while the driver calibrates. Each new
alert or escalation gets a new episode number so outputs start once per episode, not per frame.
Pure state over injected time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import AlertPattern, FusionDecision

_RANK = {
    AlertPattern.NONE: 0,
    AlertPattern.SHORT_BEEP: 1,
    AlertPattern.REPEATED: 2,
    AlertPattern.CONTINUOUS: 3,
    AlertPattern.MAX: 4,
}


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    hold_s: float = 3.0  # keep an alert until its cause has been gone this long
    cooldown_s: dict[AlertPattern, float] = field(
        default_factory=lambda: {
            AlertPattern.SHORT_BEEP: 10.0,
            AlertPattern.REPEATED: 5.0,
            AlertPattern.CONTINUOUS: 3.0,
            AlertPattern.MAX: 0.0,  # never hold back the emergency path
        }
    )


@dataclass(frozen=True, slots=True)
class PolicyOutput:
    decision: FusionDecision
    episode: int  # increments on every new alert or escalation; outputs start once per value


class AlertPolicy:
    def __init__(self, config: PolicyConfig | None = None) -> None:
        self.config = config or PolicyConfig()
        self._active = FusionDecision(AlertPattern.NONE)
        self._episode = 0
        self._cause_seen = 0.0  # last time the active alert's cause (or stronger) was present
        self._ended: dict[AlertPattern, float] = {}  # when an episode of each level ended

    @property
    def episode(self) -> int:
        return self._episode

    def update(self, now: float, raw: FusionDecision, *, calibrating: bool = False) -> PolicyOutput:
        if calibrating:  # the driver closes the eyes on purpose: nothing may alert
            self._end(now)
            return self._out()
        active = _RANK[self._active.pattern]
        rank = _RANK[raw.pattern]
        if rank > active and not self._cooling(now, raw.pattern, active):
            self._start(now, raw)
        elif active and rank >= active:
            self._cause_seen = now
            if raw.emergency and not self._active.emergency:
                self._start(now, raw)  # waiting -> emergency at MAX is an escalation: new episode
            else:  # same level: refresh reasons / flag without a new episode
                self._active = FusionDecision(self._active.pattern, raw.reasons, raw.emergency)
        elif active and now - self._cause_seen >= self.config.hold_s:
            self._end(now)
            if rank and not self._cooling(now, raw.pattern, 0):
                self._start(now, raw)
        return self._out()

    def _cooling(self, now: float, pattern: AlertPattern, active_rank: int) -> bool:
        """An alert that just ended may not restart at once, unless it escalates what is active."""
        if active_rank:
            return False  # escalation over an active alert is always allowed
        ended = self._ended.get(pattern)
        return ended is not None and now - ended < self.config.cooldown_s.get(pattern, 0.0)

    def _start(self, now: float, raw: FusionDecision) -> None:
        self._active, self._cause_seen = raw, now
        self._episode += 1

    def _end(self, now: float) -> None:
        if self._active.pattern is not AlertPattern.NONE:
            self._ended[self._active.pattern] = now
        self._active = FusionDecision(AlertPattern.NONE)

    def _out(self) -> PolicyOutput:
        return PolicyOutput(self._active, self._episode)
