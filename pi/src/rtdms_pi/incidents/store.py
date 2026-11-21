"""Incident storage, retention, and artifact indexing.

Report 4.3.1.1 compliance: No biometric data (such as raw physiology, heart rate,
or interbeat intervals) is persisted beyond the incident record. The incident
record persists only driver status and active alert states that were already
presented to the driver in the vehicle.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .avi import write_mjpeg_avi
from .ring import Entry

_ALLOWED_STATUS_KEYS = frozenset({
    "fps",
    "face",
    "state",
    "perclos",
    "openness",
    "blink_rate",
    "closure_ms",
    "calibrated",
    "calibration",
    "camera_covered",
    "call",
    "texting",
    "phone_p",
})
_ALLOWED_ALERT_KEYS = frozenset({"pattern", "reasons", "t"})
_ID_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{3}Z$")
_ALLOWED_SERVED_NAMES = frozenset({"clip.mp4", "data.jsonl", "meta.json", "clip.avi"})


def _filter_status(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k in _ALLOWED_STATUS_KEYS}


def _filter_alert(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k in _ALLOWED_ALERT_KEYS}


class IncidentStore:
    def __init__(
        self,
        root: Path,
        max_incidents: int = 20,
        min_free_mb: int = 500,
        disk_usage: Callable[[Path], Any] = shutil.disk_usage,
    ) -> None:
        self.root = Path(root)
        self.max_incidents = int(max_incidents)
        self.min_free_mb = int(min_free_mb)
        self._disk_usage = disk_usage
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._client_index: dict[str, str] = {}
        self._rebuild_client_index()

    def _rebuild_client_index(self) -> None:
        with self._lock:
            if not self.root.is_dir():
                return
            for inc_dir in self.root.iterdir():
                meta_file = inc_dir / "meta.json"
                if inc_dir.is_dir() and meta_file.is_file():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                        client_id = meta.get("client_id")
                        if isinstance(client_id, str) and client_id:
                            self._client_index[client_id] = meta.get("id", inc_dir.name)
                    except (OSError, json.JSONDecodeError):
                        continue

    def find_by_client_id(self, client_id: str) -> str | None:
        with self._lock:
            if client_id in self._client_index:
                return self._client_index[client_id]
            self._rebuild_client_index()
            return self._client_index.get(client_id)

    def _apply_retention(self) -> None:
        with self._lock:
            dirs = [d for d in self.root.iterdir() if d.is_dir()]
            if len(dirs) < self.max_incidents:
                return

            def _sort_key(d: Path) -> tuple[int, str]:
                meta_path = d / "meta.json"
                if meta_path.is_file():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        return (int(meta.get("t_crash", 0)), d.name)
                    except (OSError, json.JSONDecodeError, ValueError):
                        pass
                return (0, d.name)

            dirs.sort(key=_sort_key)
            excess = len(dirs) - self.max_incidents + 1
            for old_dir in dirs[:excess]:
                shutil.rmtree(old_dir, ignore_errors=True)
            self._client_index.clear()
            self._rebuild_client_index()

    def save_incident(
        self,
        inc_id: str,
        meta: dict[str, Any],
        entries: list[Entry],
    ) -> Path:
        target_dir = self.root / inc_id
        target_dir.mkdir(parents=True, exist_ok=True)
        meta_path = target_dir / "meta.json"
        client_id = meta.get("client_id")

        free_mb = self._disk_usage(self.root).free / (1024 * 1024)
        if free_mb < self.min_free_mb:
            disk_meta = dict(meta, id=inc_id, error="disk full", clip_ready=False, frames=0)
            meta_path.write_text(json.dumps(disk_meta, indent=2), encoding="utf-8")
            if isinstance(client_id, str) and client_id:
                with self._lock:
                    self._client_index[client_id] = inc_id
            return target_dir

        self._apply_retention()
        target_dir.mkdir(parents=True, exist_ok=True)

        jsonl_path = target_dir / "data.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for e in entries:
                row = {
                    "t": e.t_wall,
                    "status": _filter_status(e.status),
                    "alert": _filter_alert(e.alert),
                }
                f.write(json.dumps(row, separators=(",", ":")) + "\n")

        jpegs = [e.jpeg for e in entries if e.jpeg is not None]
        write_mjpeg_avi(target_dir / "clip.avi", jpegs)

        full_meta = dict(
            meta,
            id=inc_id,
            clip_ready=False,
            frames=len(jpegs),
        )
        meta_path.write_text(json.dumps(full_meta, indent=2), encoding="utf-8")
        if isinstance(client_id, str) and client_id:
            with self._lock:
                self._client_index[client_id] = inc_id
        return target_dir

    def list_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not self.root.is_dir():
            return items
        for inc_dir in self.root.iterdir():
            meta_path = inc_dir / "meta.json"
            if not inc_dir.is_dir() or not meta_path.is_file():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if "id" not in meta or "t_crash" not in meta or "g_peak" not in meta:
                continue
            is_ready = (inc_dir / "clip.mp4").is_file()
            item: dict[str, Any] = {
                "id": str(meta["id"]),
                "t_crash": int(meta["t_crash"]),
                "g_peak": float(meta["g_peak"]),
                "clip_ready": is_ready,
            }
            if meta.get("lat") is not None:
                item["lat"] = float(meta["lat"])
            elif "lat" in meta:
                item["lat"] = None
            if meta.get("lon") is not None:
                item["lon"] = float(meta["lon"])
            elif "lon" in meta:
                item["lon"] = None
            if meta.get("duration_s") is not None:
                item["duration_s"] = float(meta["duration_s"])
            items.append(item)
        items.sort(key=lambda x: int(x["t_crash"]), reverse=True)
        return items

    def path(self, inc_id: str, name: str) -> Path | None:
        if not _ID_PATTERN.match(inc_id):
            return None
        if name not in _ALLOWED_SERVED_NAMES:
            return None
        target = self.root / inc_id / name
        try:
            resolved_target = target.resolve()
            resolved_root = self.root.resolve()
            if resolved_root not in resolved_target.parents:
                return None
        except OSError:
            return None
        if not resolved_target.is_file():
            return None
        return resolved_target
