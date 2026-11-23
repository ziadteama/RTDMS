"""Hardware is opt-in; environment defaults are suitable for a development host."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    buzzer_pin: int = 18
    vibration_pin: int | None = None
    stale_s: float = 2.0
    physio_stale_s: float = 10.0
    tick_rate: float = 1.0
    http_port: int = 8080
    incident_port: int = 8081
    host: str = "::"
    state_dir: Path = Path("/var/lib/rtdms")
    rotate: int = 0
    no_camera: bool = True
    buzzer: str = "none"
    physiology: bool = False
    ble: bool | None = None
    fake_ble: bool = False
    ble_name: str = "RTDMS-Pi"
    ble_open: bool = False
    sync_system_clock: bool = False
    debug_validate: bool = False
    repo_root: Path = Path(__file__).resolve().parents[3]

    def __post_init__(self) -> None:
        if min(self.stale_s, self.physio_stale_s, self.tick_rate) <= 0:
            raise ValueError("stale seconds and tick rate must be positive")

    @classmethod
    def from_args(cls, argv: list[str] | None = None) -> RuntimeConfig:
        p = argparse.ArgumentParser(description=__doc__)
        camera = p.add_mutually_exclusive_group()
        camera.add_argument("--no-camera", dest="no_camera", action="store_true")
        camera.add_argument("--camera", dest="no_camera", action="store_false")
        p.set_defaults(no_camera=True)
        p.add_argument("--buzzer", choices=["gpio", "console", "none"], default="none")
        p.add_argument("--buzzer-pin", type=int, default=int(os.getenv("RTDMS_BUZZER_PIN", "18")))
        pin = os.getenv("RTDMS_VIBRATION_PIN")
        p.add_argument("--vibration-pin", type=int, default=int(pin) if pin else None)
        p.add_argument("--stale-s", type=float, default=float(os.getenv("RTDMS_STALE_S", "2")))
        p.add_argument(
            "--physio-stale-s", type=float, default=float(os.getenv("RTDMS_PHYSIO_STALE_S", "10"))
        )
        p.add_argument("--tick-rate", type=float, default=float(os.getenv("RTDMS_TICK_RATE", "1")))
        p.add_argument(
            "--port", dest="http_port", type=int, default=int(os.getenv("RTDMS_HTTP_PORT", "8080"))
        )
        p.add_argument(
            "--incident-port",
            type=int,
            default=int(os.getenv("RTDMS_INCIDENT_PORT", "8081")),
            help="HTTP port for incident server (default: 8081)",
        )
        p.add_argument("--host", default=os.getenv("RTDMS_HOST", "::"))
        p.add_argument(
            "--state-dir", type=Path, default=Path(os.getenv("STATE_DIRECTORY", "/var/lib/rtdms"))
        )
        p.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], default=0)
        p.add_argument("--physiology", action="store_true")
        p.add_argument("--sync-system-clock", action="store_true", default=False)
        p.add_argument("--ble", action=argparse.BooleanOptionalAction, default=None)
        p.add_argument("--fake-ble", action="store_true")
        p.add_argument("--ble-name", default=os.getenv("RTDMS_BLE_NAME", "RTDMS-Pi"))
        p.add_argument(
            "--ble-open",
            action="store_true",
            default=os.getenv("RTDMS_BLE_OPEN") == "1",
            help="DEV ONLY: accept BLE writes without a token (insecure)",
        )
        p.add_argument(
            "--debug-validate",
            action="store_true",
            default=os.getenv("RTDMS_DEBUG_VALIDATE") == "1",
        )
        return cls(**vars(p.parse_args(argv)))
