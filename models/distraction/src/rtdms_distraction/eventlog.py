"""JSONL event log: one line per behaviour start / level change / end, optionally per frame.

Local file only (privacy invariant: nothing leaves the device). No images, no landmarks.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class EventLog:
    def __init__(self, directory: str | Path, per_frame: bool = False, tag: str = "drive"):
        Path(directory).mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.path = Path(directory) / f"{tag}_{stamp}.jsonl"
        self._f = open(self.path, "a", encoding="utf8", buffering=1)  # line-buffered
        self.per_frame = per_frame
        self._open: dict[str, dict[str, Any]] = {}  # behaviour -> start record

    def write(self, record: dict[str, Any]) -> None:
        record.setdefault("wall", datetime.now(UTC).isoformat(timespec="milliseconds"))
        self._f.write(json.dumps(record, separators=(",", ":")) + "\n")

    def session(self, **info: Any) -> None:
        self.write({"event": "session_start", "mono": time.monotonic(), **info})

    def update(self, t: float, behaviours: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """Diff the smoothed states against the previous frame; log and return transitions."""
        events = []
        for name, st in behaviours.items():
            level = st["level"]
            prev = self._open.get(name)
            if level != "none" and prev is None:
                rec = {"t": round(t, 3), "event": "start", "behaviour": name, "level": level,
                       "confidence": round(st["confidence"], 3)}
                self._open[name] = {"t": t, "level": level, "peak": level}
                events.append(rec)
            elif level != "none" and prev is not None and level != prev["level"]:
                rec = {"t": round(t, 3), "event": "level", "behaviour": name, "level": level,
                       "from": prev["level"], "confidence": round(st["confidence"], 3)}
                prev["level"] = level
                if level == "alert":
                    prev["peak"] = "alert"
                events.append(rec)
            elif level == "none" and prev is not None:
                rec = {"t": round(t, 3), "event": "end", "behaviour": name,
                       "duration_s": round(t - prev["t"], 3), "peak_level": prev["peak"]}
                del self._open[name]
                events.append(rec)
        for e in events:
            self.write(e)
        return events

    def frame(self, record: dict[str, Any]) -> None:
        if self.per_frame:
            self.write({"event": "frame", **record})

    def close(self, t: float | None = None) -> None:
        if t is not None:
            for name, prev in list(self._open.items()):
                self.write({"t": round(t, 3), "event": "end", "behaviour": name,
                            "duration_s": round(t - prev["t"], 3), "peak_level": prev["peak"],
                            "reason": "session_end"})
        self.write({"event": "session_end"})
        self._f.close()
