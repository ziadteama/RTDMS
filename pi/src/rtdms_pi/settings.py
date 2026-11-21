"""Thread-safe, in-memory settings; callers validate merged candidates."""

from copy import deepcopy
from threading import RLock
from typing import Any


class SettingsStore:
    def __init__(self) -> None:
        self.lock = RLock()
        self._data: dict[str, Any] = {
            "profile": "default",
            "profiles": ["default", "driver-2"],
            "sensitivity": "normal",
            "eye_closure_s": 2.0,
            "offroad_gaze_s": 2.0,
            "phone_s": 1.0,
            "detectors": dict.fromkeys(("drowsiness", "distraction", "phone", "physiology"), True),
        }

    def read(self) -> dict[str, Any]:
        with self.lock:
            return deepcopy(self._data)

    def merged(self, subset: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            candidate = deepcopy(self._data)
            candidate.update(deepcopy(subset))
            if isinstance(subset.get("detectors"), dict):
                candidate["detectors"] = (
                    deepcopy(self._data.get("detectors", {})) | subset["detectors"]
                )
            return candidate

    def update(self, validated: dict[str, Any]) -> None:
        with self.lock:
            self._data = self.merged(validated)
