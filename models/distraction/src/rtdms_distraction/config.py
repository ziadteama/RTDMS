"""YAML configuration -> typed dataclasses.

Two files: `pipeline.yaml` (capture, rectification, networks, logging) and `rules.yaml`
(behaviour thresholds). Unknown keys raise, so a typo in a threshold name fails loudly instead
of silently running on the default.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # models/distraction/
CONFIG_DIR = PACKAGE_ROOT / "configs"

BEHAVIOURS = ("phone_right_ear", "phone_left_ear", "phone_in_hand", "drinking", "eating")
OBJECT_CLASSES = ("phone", "drink", "food", "hand")


def resolve_path(p: str | Path) -> Path:
    """Relative paths in configs are relative to models/distraction/."""
    path = Path(p)
    return path if path.is_absolute() else (PACKAGE_ROOT / path).resolve()


# --------------------------------------------------------------------------- pipeline


@dataclass
class CaptureConfig:
    width: int = 1296
    height: int = 972
    fps: int = 30
    flip_horizontal: bool = False
    # OpenCV webcam backend: auto (MSMF, then DSHOW on Windows) | msmf | dshow | any
    backend: str = "auto"
    # Detector / face mesh see grayscale (matches the IR camera). Live mode can toggle it.
    grayscale: bool = True


@dataclass
class RectifyConfig:
    enabled: bool = True
    calibration_file: str = "configs/camera_fisheye.yaml"


@dataclass
class RoiConfig:
    rect: list[int] | None = None
    output_width: int = 640
    output_height: int = 640
    mask_polygons: list[list[list[float]]] = field(default_factory=list)


@dataclass
class DetectorConfig:
    backend: str = "ncnn"
    weights: str = "models/yolo26n_coco_416_ncnn_model"
    imgsz: int = 416
    num_threads: int = 2
    every_n: int = 1
    class_map: dict[str, str] = field(default_factory=dict)
    conf: dict[str, float] = field(default_factory=dict)
    nms_iou: float = 0.5


@dataclass
class FaceMeshConfig:
    backend: str = "mediapipe"
    dms_face_backend: str = "litert"
    model_path: str = "../face/models/face_landmarker.task"
    min_face_detection_confidence: float = 0.5
    min_face_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    crop_size: int = 256
    crop_scale: float = 2.2
    search_region: list[float] = field(default_factory=lambda: [0.0, 0.0, 1.0, 0.7])
    search_tile: float = 0.45
    lost_reset_frames: int = 5


@dataclass
class HandsConfig:
    source: str = "mediapipe"
    model_path: str = "models/hand_landmarker.task"
    num_hands: int = 2
    min_detection_confidence: float = 0.5
    every_n: int = 2
    pad: float = 0.25


@dataclass
class EventLogConfig:
    dir: str = "logs"
    per_frame: bool = False


@dataclass
class ThreadsConfig:
    opencv: int = 1


@dataclass
class LiveModel:
    name: str
    weights: str
    backend: str = "ncnn"
    imgsz: int = 416
    # mediapipe for COCO models (no hand class); detector for fine-tuned ones.
    hands: str = "mediapipe"


@dataclass
class LiveConfig:
    """scripts/live.py only."""

    # Process at most this many frames per second (mimic the Pi). None = as fast as possible.
    fps_cap: float | None = None
    # At startup: "touch your RIGHT ear" for side_check_s seconds; flips the image if the
    # face-side mapping comes out reversed (mirrored webcam).
    side_check: bool = False
    side_check_s: float = 5.0
    conf_step: float = 0.05
    models: list[LiveModel] = field(default_factory=list)


@dataclass
class PipelineConfig:
    driver_side: str = "right"
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    rectify: RectifyConfig = field(default_factory=RectifyConfig)
    roi: RoiConfig = field(default_factory=RoiConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    facemesh: FaceMeshConfig = field(default_factory=FaceMeshConfig)
    hands: HandsConfig = field(default_factory=HandsConfig)
    eventlog: EventLogConfig = field(default_factory=EventLogConfig)
    threads: ThreadsConfig = field(default_factory=ThreadsConfig)
    live: LiveConfig = field(default_factory=LiveConfig)

    def __post_init__(self) -> None:
        if self.driver_side not in ("right", "left"):
            raise ValueError(f"driver_side must be 'right' or 'left', got {self.driver_side!r}")


# --------------------------------------------------------------------------- rules


@dataclass
class BaselineConfig:
    duration_s: float = 10.0
    min_samples: int = 30


@dataclass
class HeadDownConfig:
    pitch_deg: float = 15.0
    gaze_down: float = 0.25
    gaze_down_iris: float = 0.12


@dataclass
class EarZoneConfig:
    outward: float = 0.30
    down: float = 0.15
    half_width: float = 0.45
    half_height: float = 0.65
    inward: float = 0.0
    hand_only: bool = False
    hand_only_confidence: float = 0.6


@dataclass
class EarsConfig:
    near: EarZoneConfig = field(default_factory=EarZoneConfig)
    far: EarZoneConfig = field(
        default_factory=lambda: EarZoneConfig(
            outward=0.20, half_width=0.50, inward=0.35, hand_only=True
        )
    )
    min_overlap: float = 0.25


@dataclass
class PhoneInHandConfig:
    below_chin: float = -0.10
    hand_max_gap: float = 0.30
    require_hand: bool = True
    holder_zones: list[list[float]] = field(default_factory=list)
    alert_after_down_s: float = 2.0


@dataclass
class DrinkingConfig:
    mouth_half_width: float = 0.40
    mouth_half_height: float = 0.35
    min_overlap: float = 0.15
    pitch_up_deg: float = 8.0
    pitch_up_bonus: float = 1.25


@dataclass
class ChewingConfig:
    window_s: float = 3.0
    min_span_s: float = 2.0
    resample_hz: float = 15.0
    band_hz: list[float] = field(default_factory=lambda: [0.8, 2.5])
    min_band_fraction: float = 0.45
    min_amplitude_blendshape: float = 0.02
    min_amplitude_geometric: float = 0.008
    lips_closed_ratio: float = 0.10
    min_lips_closed_fraction: float = 0.6


@dataclass
class EatingConfig:
    food_mouth_max_dist: float = 0.80
    food_memory_s: float = 5.0
    chewing: ChewingConfig = field(default_factory=ChewingConfig)


@dataclass
class SmoothingConfig:
    window_s: float = 1.75
    on_ratio: float = 0.70
    off_ratio: float = 0.30
    min_coverage: float = 0.6
    face_lost_hold_s: float = 5.0


@dataclass
class RulesConfig:
    baseline: BaselineConfig = field(default_factory=BaselineConfig)
    head_down: HeadDownConfig = field(default_factory=HeadDownConfig)
    ears: EarsConfig = field(default_factory=EarsConfig)
    phone_in_hand: PhoneInHandConfig = field(default_factory=PhoneInHandConfig)
    drinking: DrinkingConfig = field(default_factory=DrinkingConfig)
    eating: EatingConfig = field(default_factory=EatingConfig)
    smoothing: SmoothingConfig = field(default_factory=SmoothingConfig)
    levels: dict[str, str] = field(
        default_factory=lambda: {
            "phone_right_ear": "alert",
            "phone_left_ear": "alert",
            "phone_in_hand": "warning",
            "drinking": "warning",
            "eating": "warning",
        }
    )

    def __post_init__(self) -> None:
        for name, level in self.levels.items():
            if name not in BEHAVIOURS:
                raise ValueError(f"levels: unknown behaviour {name!r}")
            if level not in ("warning", "alert"):
                raise ValueError(f"levels.{name}: must be 'warning' or 'alert', got {level!r}")


# --------------------------------------------------------------------------- loading


def _build(cls: type, data: Any, where: str) -> Any:
    """Recursively instantiate dataclass `cls` from a plain dict, rejecting unknown keys."""
    if data is None:
        return cls()
    if not isinstance(data, dict):
        raise TypeError(f"{where}: expected a mapping, got {type(data).__name__}")
    hints = typing.get_type_hints(cls)
    names = {f.name for f in dataclasses.fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise KeyError(f"{where}: unknown key(s) {sorted(unknown)}")
    kwargs = {}
    for key, value in data.items():
        hint = hints[key]
        target = _dataclass_in(hint)
        item = _list_item_dataclass(hint)
        if target:
            kwargs[key] = _build(target, value, f"{where}.{key}")
        elif item and isinstance(value, list):
            kwargs[key] = [_build(item, v, f"{where}.{key}[{i}]") for i, v in enumerate(value)]
        else:
            kwargs[key] = value
    return cls(**kwargs)


def _dataclass_in(hint: Any) -> type | None:
    if dataclasses.is_dataclass(hint):
        return hint
    if isinstance(hint, types.UnionType) or typing.get_origin(hint) is typing.Union:
        for arg in typing.get_args(hint):
            if dataclasses.is_dataclass(arg):
                return arg
    return None


def _list_item_dataclass(hint: Any) -> type | None:
    if typing.get_origin(hint) is list:
        (arg,) = typing.get_args(hint) or (None,)
        if dataclasses.is_dataclass(arg):
            return arg
    return None


def _read_yaml(path: str | Path) -> dict:
    with open(path, encoding="utf8") as f:
        return yaml.safe_load(f) or {}


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        both = isinstance(v, dict) and isinstance(out.get(k), dict)
        out[k] = deep_merge(out[k], v) if both else v
    return out


def profile_path(profile: str | Path) -> Path:
    """A profile name (configs/profiles/<name>.yaml) or a path."""
    p = Path(profile)
    return p if p.suffix in (".yaml", ".yml") else CONFIG_DIR / "profiles" / f"{profile}.yaml"


def load_pipeline_config(path: str | Path | None = None,
                         profile: str | Path | None = None) -> PipelineConfig:
    """pipeline.yaml (or `path`), with an optional profile deep-merged over it."""
    path = Path(path) if path else CONFIG_DIR / "pipeline.yaml"
    data = _read_yaml(path)
    name = path.name
    if profile:
        pp = profile_path(profile)
        data = deep_merge(data, _read_yaml(pp))
        name = f"{path.name}+{pp.name}"
    return _build(PipelineConfig, data, name)


def load_rules_config(path: str | Path | None = None) -> RulesConfig:
    path = Path(path) if path else CONFIG_DIR / "rules.yaml"
    return _build(RulesConfig, _read_yaml(path), path.name)


def save_roi_rect(rect: list[int], path: str | Path | None = None) -> None:
    """Write roi.rect back into pipeline.yaml, keeping every comment except the replaced line."""
    path = Path(path) if path else CONFIG_DIR / "pipeline.yaml"
    lines = Path(path).read_text(encoding="utf8").splitlines(keepends=True)
    in_roi = False
    for i, line in enumerate(lines):
        if line.startswith("roi:"):
            in_roi = True
            continue
        if in_roi and line and not line[0].isspace() and not line.startswith("#"):
            break
        if in_roi and line.strip().startswith("rect:"):
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f"{indent}rect: [{', '.join(str(int(v)) for v in rect)}]\n"
            Path(path).write_text("".join(lines), encoding="utf8")
            return
    raise KeyError(f"{path}: could not find roi.rect to update")
