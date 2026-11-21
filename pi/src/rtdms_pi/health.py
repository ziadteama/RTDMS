"""System and pipeline health probe conforming to contract v1."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .ble.contract import CONTRACT_VERSION
from .config import RuntimeConfig
from .sources import NullPhysioSource, PhysioSource
from .state import RuntimeState, Snapshot


def parse_throttled(output: str) -> int | None:
    match = re.search(r"throttled=(0x[0-9a-fA-F]+|[0-9]+)", output)
    if match:
        try:
            return int(match.group(1), 0)
        except ValueError:
            return None
    try:
        return int(output.strip(), 0) if output.strip() else None
    except ValueError:
        return None


def parse_volts_5v(output: str) -> float | None:
    match = re.search(r"=\s*([0-9]+(?:\.[0-9]+)?)", output) or re.search(
        r"([0-9]+\.[0-9]+)", output
    )
    if match:
        try:
            return round(float(match.group(1)), 2)
        except ValueError:
            return None
    return None


def parse_cpu_stat(lines: str) -> tuple[int, int] | None:
    for line in lines.splitlines():
        if line.startswith("cpu "):
            parts = [int(p) for p in line.split()[1:]]
            if len(parts) >= 4:
                idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
                return idle, sum(parts)
    return None


def parse_meminfo(lines: str) -> tuple[int, int] | None:
    total_kb: int | None = None
    avail_kb: int | None = None
    free_kb = buffers_kb = cached_kb = 0
    for line in lines.splitlines():
        if line.startswith("MemTotal:"):
            total_kb = int(line.split()[1])
        elif line.startswith("MemAvailable:"):
            avail_kb = int(line.split()[1])
        elif line.startswith("MemFree:"):
            free_kb = int(line.split()[1])
        elif line.startswith("Buffers:"):
            buffers_kb = int(line.split()[1])
        elif line.startswith("Cached:"):
            cached_kb = int(line.split()[1])
    if total_kb is not None:
        avail = avail_kb if avail_kb is not None else free_kb + buffers_kb + cached_kb
        return total_kb // 1024, avail // 1024
    return None


def parse_uptime(line: str) -> int | None:
    try:
        return int(float(line.split()[0]))
    except (ValueError, IndexError):
        return None


def parse_temp_c(line: str) -> float | None:
    try:
        val = float(line.strip())
        return round(val / 1000.0 if val > 1000 else val, 1)
    except (ValueError, AttributeError):
        return None


class HealthProbe:
    def __init__(
        self,
        *,
        state: RuntimeState | None = None,
        settings_provider: Callable[[], Mapping[str, Any]] | None = None,
        physio_source: PhysioSource | None = None,
        config: RuntimeConfig | None = None,
        state_dir: Path | str = Path("/var/lib/rtdms"),
        run: Callable[..., Any] = subprocess.run,
        read_text: Callable[[Path | str], str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        disk_usage: Callable[[Path | str], Any] = shutil.disk_usage,
    ) -> None:
        self.state, self.settings_provider = state, settings_provider
        self.physio_source, self.config = physio_source, config
        self.state_dir = Path(state_dir)
        self.run = run
        self._read_text = read_text or (lambda p: Path(p).read_text(encoding="utf-8"))
        self.clock, self.disk_usage = clock, disk_usage
        self._started = clock()
        self._prev_cpu: tuple[int, int] | None = None

    def _run_cmd(self, cmd: list[str]) -> str:
        try:
            res = self.run(cmd, capture_output=True, text=True, check=False)
            return str(res.stdout if hasattr(res, "stdout") else res)
        except Exception:
            return ""

    def _probe_cpu(self) -> float:
        try:
            parsed = parse_cpu_stat(self._read_text("/proc/stat"))
            if parsed is None:
                return 0.0
            idle, total = parsed
            if self._prev_cpu is None:
                self._prev_cpu = (idle, total)
                return 0.0
            prev_idle, prev_total = self._prev_cpu
            delta_total, delta_idle = total - prev_total, idle - prev_idle
            self._prev_cpu = (idle, total)
            if delta_total > 0:
                pct = 100.0 * (delta_total - delta_idle) / delta_total
                return max(0.0, min(100.0, round(pct, 1)))
        except Exception:
            pass
        return 0.0

    def _probe_wifi(self) -> str:
        out_nm = self._run_cmd(["nmcli", "-t", "-f", "GENERAL.STATE", "con", "show", "rtdms-ap"])
        if "activated" in out_nm:
            out_iw = self._run_cmd(["iw", "dev", "wlan0", "station", "dump"])
            count = sum(1 for line in out_iw.splitlines() if "station" in line.lower())
            return "clients" if count > 0 else "on"
        return "off"

    def _probe_models(self, s: Snapshot) -> dict[str, str]:
        settings = self.settings_provider() if self.settings_provider else None
        dets = settings.get("detectors") if isinstance(settings, Mapping) else {}
        dets = dets if isinstance(dets, Mapping) else {}

        drowsy_on = dets.get("drowsiness", True) is not False
        distract_on = (
            dets.get("distraction", True) is not False and dets.get("phone", True) is not False
        )
        physio_on = dets.get("physiology", True) is not False
        cfg = self.config or RuntimeConfig()

        models: dict[str, str] = {"fusion": "running"}
        models["face"] = (
            "off" if not drowsy_on or cfg.no_camera else "running" if s.camera_ok else "error"
        )
        models["distraction"] = (
            "off" if not distract_on or cfg.no_camera else "running" if s.camera_ok else "error"
        )
        if not physio_on:
            models["physiology"] = "off"
        elif (
            self.physio_source is None
            or isinstance(self.physio_source, NullPhysioSource)
            or (not cfg.physiology and not getattr(cfg, "ble", False))
        ):
            models["physiology"] = "off"
        else:
            models["physiology"] = "running" if s.physio is not None else "error"
        return models

    def probe(self, snapshot: Snapshot | None = None) -> dict[str, Any]:
        s = (
            snapshot
            if snapshot is not None
            else (self.state.snapshot() if self.state else Snapshot())
        )
        try:
            temp_c = parse_temp_c(self._read_text("/sys/class/thermal/thermal_zone0/temp"))
        except Exception:
            temp_c = s.temp_c

        throttled = parse_throttled(self._run_cmd(["vcgencmd", "get_throttled"]))
        volts_5v = parse_volts_5v(self._run_cmd(["vcgencmd", "pmic_read_adc", "EXT5V_V"]))

        mem_used = mem_total = None
        try:
            mem = parse_meminfo(self._read_text("/proc/meminfo"))
            if mem is not None:
                mem_total, avail = mem
                mem_used = max(0, mem_total - avail)
        except Exception:
            pass

        disk_free = None
        try:
            usage = self.disk_usage(self.state_dir)
            if hasattr(usage, "free"):
                disk_free = int(usage.free) // (1024 * 1024)
        except Exception:
            pass

        uptime_s = int(self.clock() - self._started)
        try:
            up = parse_uptime(self._read_text("/proc/uptime"))
            if up is not None:
                uptime_s = up
        except Exception:
            pass

        d: dict[str, Any] = {
            "contract": CONTRACT_VERSION,
            "cpu_pct": self._probe_cpu(),
            "fps": float(s.fps),
            "uptime_s": uptime_s,
            "camera": "ok" if s.camera_ok else "lost",
            "models": self._probe_models(s),
            "wifi": self._probe_wifi(),
            "temp_c": temp_c,
            "volts_5v": volts_5v,
        }
        if throttled is not None:
            d["throttled"] = throttled
        if mem_used is not None:
            d["mem_used_mb"] = mem_used
        if mem_total is not None:
            d["mem_total_mb"] = mem_total
        if disk_free is not None:
            d["disk_free_mb"] = disk_free
        return d

    def __call__(self) -> dict[str, Any]:
        return self.probe()
