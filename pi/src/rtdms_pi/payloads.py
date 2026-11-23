"""Compact contract v1 payloads; no model decisions are made here."""

from __future__ import annotations

import json
from collections.abc import Mapping

from dms_fusion import FusionDecision

from .clock import PhoneClock
from .sources import number
from .state import DecisionSnapshot, Snapshot


def to_json_bytes(d: Mapping[str, object]) -> bytes:
    return json.dumps(dict(d), separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(
        "utf-8"
    )


def _budget(d: dict[str, object], optional: list[str]) -> dict[str, object]:
    for key in reversed(optional):
        if len(to_json_bytes(d)) <= 240:
            break
        d.pop(key, None)
    if len(to_json_bytes(d)) > 240:
        raise ValueError("required payload fields exceed 240 bytes")
    return d


def alert_payload(
    decision: FusionDecision | DecisionSnapshot, mono_s: float, clock: PhoneClock
) -> dict[str, object]:
    t, t_src = clock.payload_t(mono_s)
    reasons = [r[:48] for r in decision.reasons[:4]]
    d: dict[str, object] = {
        "pattern": decision.pattern.value,
        "reasons": reasons,
        "t": round(t, 3),
        "t_src": t_src,
    }
    if decision.emergency == "unresponsive":
        d["emergency"] = "unresponsive"
    episode = getattr(decision, "episode", 0)
    if episode:
        d["episode"] = episode
    while reasons and len(to_json_bytes(d)) > 240:
        reasons[-1] = reasons[-1][:-1]
        if not reasons[-1]:
            reasons.pop()
    return _budget(d, [])


def status_payload(
    snapshot: Snapshot, settings: Mapping[str, object] | None = None
) -> dict[str, object]:
    s, f, p = snapshot, snapshot.face, snapshot.phone
    if settings is not None:
        from .detector_gate import apply_settings

        f, p, _ = apply_settings(settings, f, p, None)
    state = f.state if f and f.face and s.camera_ok else "unavailable"
    if state not in {"starting", "unavailable", "alert", "distracted", "warning", "drowsy"}:
        state = "unavailable"
    d: dict[str, object] = {
        "fps": number(s.fps) or 0.0,
        "face": bool(f and f.face and s.camera_ok),
        "state": state,
    }
    optional = [
        "perclos",
        "openness",
        "blink_rate",
        "closure_ms",
        "calibrated",
        "calibration",
        "calibration_step",
        "calibration_left_s",
        "camera_covered",
        "call",
        "texting",
        "phone_p",
        "temp_c",
    ]
    if f:
        if f.face and s.camera_ok:
            for key in ("perclos", "openness", "blink_rate", "closure_ms"):
                value = number(getattr(f, key))
                if value is not None:
                    d[key] = value
        if f.calibrated is not None:
            d["calibrated"] = f.calibrated
        if f.calibration in ("ok", "calibrating", "failed", "lost"):
            d["calibration"] = f.calibration
        if f.calibration_step is not None:
            d["calibration_step"] = f.calibration_step
            if number(f.calibration_left_s) is not None:
                d["calibration_left_s"] = round(float(f.calibration_left_s or 0.0), 1)
    if p:
        d.update(call=p.call, texting=p.texting, phone_p=number(p.phone_p))
    if number(s.temp_c) is not None:
        d["temp_c"] = s.temp_c
    return _budget(d, optional)


def physio_payload(snapshot: Snapshot, clock: PhoneClock) -> dict[str, object]:
    p = snapshot.physio
    t, t_src = clock.payload_t(p.t if p else snapshot.t)
    d: dict[str, object] = {"watch_connected": False, "t": round(t, 3), "t_src": t_src}
    if p is None:
        return d
    raw = p.raw
    d["watch_connected"] = raw.get("watch_connected") is True
    # Preserve HR context first; diagnostics and beat arrays yield to the notify budget.
    numeric = ["hr_bpm", "hr_baseline_bpm", "hr_delta_bpm", "hr_trend_bpm_per_10min"]
    optional = ["hr_bpm", "quality", "worn", *numeric[1:], "hrv_state", "rmssd_ms", "rr_ms"]
    for key in [*numeric, "rmssd_ms"]:
        if key in raw:
            value = number(raw[key])
            d[key] = round(value, 1) if value is not None else None
    if isinstance(raw.get("worn"), bool):
        d["worn"] = raw["worn"]
    rr = raw.get("rr_ms")
    if isinstance(rr, (tuple, list)):
        d["rr_ms"] = [number(v) for v in rr[:8] if number(v) is not None]
    if raw.get("hrv_state") in ("warmup", "valid", "degraded", "bad", "stale"):
        d["hrv_state"] = raw["hrv_state"]
    if raw.get("quality") in ("good", "degraded", "bad"):
        d["quality"] = raw["quality"]
    return _budget(d, optional)


def health_payload(
    *,
    cpu_pct: float,
    fps: float,
    uptime_s: float,
    camera: bool,
    models: Mapping[str, str],
    temp_c: float | None = None,
    throttled: int | None = None,
    volts_5v: float | None = None,
    mem_used_mb: int | None = None,
    mem_total_mb: int | None = None,
    disk_free_mb: int | None = None,
    wifi: str | None = None,
    physio_diag: Mapping[str, object] | None = None,
) -> dict[str, object]:
    d: dict[str, object] = {
        "cpu_pct": cpu_pct,
        "fps": fps,
        "uptime_s": int(uptime_s),
        "camera": "ok" if camera else "lost",
        "models": dict(models),
        "contract": 1,
    }
    for key, value in (
        ("temp_c", temp_c),
        ("throttled", throttled),
        ("volts_5v", volts_5v),
        ("mem_used_mb", mem_used_mb),
        ("mem_total_mb", mem_total_mb),
        ("disk_free_mb", disk_free_mb),
        ("wifi", wifi),
    ):
        if value is not None:
            d[key] = value
    if physio_diag is not None:
        d["physio_diag"] = {
            "shadow_agree": None,
            "shadow_disagree": None,
            "shadow_only": None,
            **physio_diag,
        }
    return d
