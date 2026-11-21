from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from rtdms_pi.ble.contract import validate
from rtdms_pi.config import RuntimeConfig
from rtdms_pi.health import (
    HealthProbe,
    parse_cpu_stat,
    parse_meminfo,
    parse_temp_c,
    parse_throttled,
    parse_uptime,
    parse_volts_5v,
)
from rtdms_pi.payloads import to_json_bytes
from rtdms_pi.sources import GarminPhysioSource, NullPhysioSource
from rtdms_pi.state import FaceReport, PhysioReport, RuntimeState


def test_parsers() -> None:
    assert parse_throttled("throttled=0x50005") == 0x50005
    assert parse_throttled("throttled=0x0\n") == 0
    assert parse_throttled("invalid") is None

    assert parse_volts_5v("EXT5V_V volt=5.0800V\n") == 5.08
    assert parse_volts_5v("volt=5.12V") == 5.12
    assert parse_volts_5v("invalid") is None

    assert parse_uptime("3725.12 14820.48\n") == 3725
    assert parse_uptime("") is None

    assert parse_temp_c("66100\n") == 66.1
    assert parse_temp_c("45.2\n") == 45.2
    assert parse_temp_c("bad") is None

    cpu_text = "cpu  100 20 50 800 10 5 2 0 0 0\ncpu0 50 10 25 400 5 2 1 0 0 0"
    parsed_cpu = parse_cpu_stat(cpu_text)
    assert parsed_cpu is not None
    idle, total = parsed_cpu
    assert idle == 800 + 10  # idle + iowait
    assert total == 100 + 20 + 50 + 800 + 10 + 5 + 2

    mem_text = "MemTotal:        8257256 kB\nMemAvailable:    6067160 kB\n"
    parsed_mem = parse_meminfo(mem_text)
    assert parsed_mem is not None
    assert parsed_mem[0] == 8257256 // 1024
    assert parsed_mem[1] == 6067160 // 1024


def test_health_probe_full_simulation(tmp_path: Path) -> None:
    files = {
        "/proc/stat": "cpu  100 0 50 850 0 0 0 0 0 0\n",
        "/proc/meminfo": "MemTotal: 8388608 kB\nMemAvailable: 4194304 kB\n",
        "/proc/uptime": "1234.56 5000.0\n",
        "/sys/class/thermal/thermal_zone0/temp": "55000\n",
    }

    commands = {
        ("vcgencmd", "get_throttled"): SimpleNamespace(
            stdout="throttled=0x50005\n", returncode=0
        ),
        ("vcgencmd", "pmic_read_adc", "EXT5V_V"): SimpleNamespace(
            stdout="EXT5V_V volt=5.0800V\n", returncode=0
        ),
        ("nmcli", "-t", "-f", "GENERAL.STATE", "con", "show", "rtdms-ap"): SimpleNamespace(
            stdout="GENERAL.STATE:activated\n", returncode=0
        ),
        ("iw", "dev", "wlan0", "station", "dump"): SimpleNamespace(
            stdout="Station aa:bb:cc:dd:ee:ff (on wlan0)\n", returncode=0
        ),
    }

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        return commands.get(tuple(cmd), SimpleNamespace(stdout="", returncode=1))

    def fake_read(path: Path | str) -> str:
        p = str(path)
        if p in files:
            return files[p]
        raise FileNotFoundError(p)

    def fake_disk(path: Path | str) -> Any:
        return SimpleNamespace(free=42 * 1024 * 1024 * 1024)

    state = RuntimeState()
    now = time.monotonic()
    state.update_frame(FaceReport(face=True), None, 15.0, 55.0, True, now)

    all_detectors = {
        "detectors": {"drowsiness": True, "distraction": True, "physiology": True}
    }
    probe = HealthProbe(
        state=state,
        settings_provider=lambda: all_detectors,
        physio_source=GarminPhysioSource(),
        config=RuntimeConfig(host="127.0.0.1", http_port=0, no_camera=False, physiology=True),
        state_dir=tmp_path,
        run=fake_run,
        read_text=fake_read,
        disk_usage=fake_disk,
    )

    # First call: cpu_pct must be 0.0
    payload1 = probe()
    assert payload1["cpu_pct"] == 0.0
    assert payload1["throttled"] == 0x50005
    assert payload1["volts_5v"] == 5.08
    assert payload1["temp_c"] == 55.0
    assert payload1["wifi"] == "clients"
    assert payload1["uptime_s"] == 1234
    assert payload1["mem_total_mb"] == 8192
    assert payload1["mem_used_mb"] == 4096
    assert payload1["disk_free_mb"] == 42 * 1024
    assert payload1["camera"] == "ok"
    assert payload1["models"]["face"] == "running"
    assert payload1["models"]["distraction"] == "running"
    assert payload1["models"]["fusion"] == "running"
    assert payload1["models"]["physiology"] == "error"  # Garmin configured but no physio report yet

    # Validate against contract schema
    assert validate("health", payload1) is not None
    assert len(to_json_bytes(payload1)) <= 512

    # Second call: change cpu stats
    files["/proc/stat"] = "cpu  200 0 100 900 0 0 0 0 0 0\n"
    # delta total = (200+100+900) - (100+50+850) = 1200 - 1000 = 200
    # delta idle = 900 - 850 = 50
    # cpu_pct = 100 * (200 - 50) / 200 = 75.0%
    payload2 = probe()
    assert payload2["cpu_pct"] == 75.0
    assert validate("health", payload2) is not None
    assert len(to_json_bytes(payload2)) <= 512


def test_health_probe_failures_graceful() -> None:
    def failing_run(cmd: list[str], **kwargs: Any) -> Any:
        raise OSError("command not found")

    def failing_read(path: Path | str) -> str:
        raise OSError("file not found")

    def failing_disk(path: Path | str) -> Any:
        raise OSError("disk error")

    state = RuntimeState()
    probe = HealthProbe(
        state=state,
        run=failing_run,
        read_text=failing_read,
        disk_usage=failing_disk,
        clock=lambda: 100.0,
    )
    payload = probe()
    assert payload["cpu_pct"] == 0.0
    assert payload["volts_5v"] is None
    assert "throttled" not in payload
    assert "mem_used_mb" not in payload
    assert "mem_total_mb" not in payload
    assert "disk_free_mb" not in payload
    assert payload["wifi"] == "off"
    assert payload["camera"] == "lost"
    assert payload["fps"] == 0.0
    assert payload["models"] == {
        "fusion": "running",
        "face": "off",
        "distraction": "off",
        "physiology": "off",
    }
    assert validate("health", payload) is not None
    assert len(to_json_bytes(payload)) <= 512


def test_health_models_capabilities() -> None:
    state = RuntimeState()
    now = time.monotonic()
    state.update_frame(FaceReport(face=True), None, 14.0, 50.0, True, now)
    state.update_physio(PhysioReport({"hr_bpm": 70}, now))

    # All enabled, camera ok, physio ok
    all_detectors = {
        "detectors": {"drowsiness": True, "distraction": True, "physiology": True}
    }
    probe = HealthProbe(
        state=state,
        settings_provider=lambda: all_detectors,
        physio_source=GarminPhysioSource(),
        config=RuntimeConfig(no_camera=False, physiology=True),
    )
    p = probe()
    assert p["models"] == {
        "fusion": "running",
        "face": "running",
        "distraction": "running",
        "physiology": "running",
    }

    # Disable drowsiness via settings
    no_drowsy = {
        "detectors": {"drowsiness": False, "distraction": True, "physiology": True}
    }
    probe_no_drowsy = HealthProbe(
        state=state,
        settings_provider=lambda: no_drowsy,
        physio_source=GarminPhysioSource(),
        config=RuntimeConfig(no_camera=False, physiology=True),
    )
    assert probe_no_drowsy()["models"]["face"] == "off"
    assert probe_no_drowsy()["models"]["distraction"] == "running"

    # Disable distraction via settings
    no_distract = {
        "detectors": {"drowsiness": True, "distraction": False, "physiology": True}
    }
    probe_no_distract = HealthProbe(
        state=state,
        settings_provider=lambda: no_distract,
        physio_source=GarminPhysioSource(),
        config=RuntimeConfig(no_camera=False, physiology=True),
    )
    assert probe_no_distract()["models"]["distraction"] == "off"

    # Disable physiology via settings
    no_physio = {
        "detectors": {"drowsiness": True, "distraction": True, "physiology": False}
    }
    probe_no_physio = HealthProbe(
        state=state,
        settings_provider=lambda: no_physio,
        physio_source=GarminPhysioSource(),
        config=RuntimeConfig(no_camera=False, physiology=True),
    )
    assert probe_no_physio()["models"]["physiology"] == "off"

    # NullPhysioSource
    probe_null_physio = HealthProbe(
        state=state,
        settings_provider=lambda: all_detectors,
        physio_source=NullPhysioSource(),
        config=RuntimeConfig(no_camera=False, physiology=False),
    )
    assert probe_null_physio()["models"]["physiology"] == "off"
