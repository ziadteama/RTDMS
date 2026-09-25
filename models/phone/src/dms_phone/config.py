"""Tunables for Pi-first phone distraction inference."""

from __future__ import annotations

from dataclasses import dataclass, field

# State Farm c0..c9 → RTDMS {safe, phone, eating}
# c1–c4 phone/text; c6 drinking ≈ eating; rest → safe for v1.
STATEFARM_COLLAPSE: dict[str, str] = {
    "c0": "safe",
    "c1": "phone",
    "c2": "phone",
    "c3": "phone",
    "c4": "phone",
    "c5": "safe",
    "c6": "eating",
    "c7": "safe",
    "c8": "safe",
    "c9": "safe",
}


@dataclass
class DetectorConfig:
    # 5 Hz meets "alert within 1 s" with headroom; do not raise without a Pi bench.
    infer_hz: float = 5.0
    input_size: int = 224
    phone_threshold: float = 0.55
    eating_threshold: float = 0.55
    min_confidence: float = 0.40
    # Open Safe-Drive-TN YOLOv8n-cls (State Farm), exported ONNX — no local train required.
    model_path: str = "models/phone_cls.onnx"
    model_version: str = "0.2.0-statefarm-hf"
    # ONNX logit order from Safe-Drive-TN / State Farm.
    class_names: tuple[str, ...] = (
        "c0",
        "c1",
        "c2",
        "c3",
        "c4",
        "c5",
        "c6",
        "c7",
        "c8",
        "c9",
    )
    collapse_map: dict[str, str] = field(default_factory=lambda: dict(STATEFARM_COLLAPSE))


@dataclass
class FusionConfig:
    socket_path: str = "/run/dms-phone.sock"


@dataclass
class Config:
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    fusion: FusionConfig = field(default_factory=FusionConfig)
    schema_version: int = 1
