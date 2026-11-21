"""Thread-safe, persistent settings; callers validate merged candidates."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any


class SettingsStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.lock = RLock()
        self.path = Path(path) if path is not None else None
        self._data: dict[str, Any] = {
            "profile": "default",
            "profiles": ["default", "driver-2"],
            "sensitivity": "normal",
            "eye_closure_s": 2.0,
            "offroad_gaze_s": 2.0,
            "phone_s": 1.0,
            "detectors": dict.fromkeys(("drowsiness", "distraction", "phone", "physiology"), True),
        }
        if self.path is not None and self.path.is_file():
            self._load()

    def _load(self) -> None:
        assert self.path is not None
        try:
            content = self.path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                self._data = self.merged(data)
        except Exception:
            pass

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
            if self.path is not None:
                self._save()

    def _save(self) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise
