from __future__ import annotations

import os
import subprocess
from pathlib import Path

SYSTEMD = Path(__file__).resolve().parents[1] / "deploy" / "systemd"
UNIT = SYSTEMD / "rtdms-pi-user.service"
SCRIPT = SYSTEMD / "install-user-service.sh"


def _run(tmp_path: Path, *args: str, fake: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RTDMS_UNIT_DIR"] = str(tmp_path / "units")
    if fake:
        bindir = tmp_path / "bin"
        bindir.mkdir(exist_ok=True)
        fake_ctl = bindir / "systemctl"
        fake_ctl.write_text(f'#!/bin/sh\necho "$@" >> "{tmp_path}/calls.log"\n')
        fake_ctl.chmod(0o755)
        env["PATH"] = f"{bindir}:{env['PATH']}"
    return subprocess.run([str(SCRIPT), *args], capture_output=True, text=True, env=env, check=True)


def _calls(tmp_path: Path) -> list[str]:
    return (tmp_path / "calls.log").read_text().splitlines()


def test_unit_contents() -> None:
    text = UNIT.read_text()
    assert "--no-camera --ble --buzzer none --port 8090" in text
    assert "Environment=STATE_DIRECTORY=%h/.local/state/rtdms" in text
    for line in (
        "Restart=on-failure",
        "Nice=10",
        "CPUWeight=20",
        "IOSchedulingClass=idle",
        "WantedBy=default.target",
    ):
        assert line in text
    assert "password" not in text.lower()
    assert "secret" not in text.lower()


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    res = _run(tmp_path, "--dry-run")
    assert "enable" in res.stdout
    assert not (tmp_path / "units").exists()


def test_install(tmp_path: Path) -> None:
    _run(tmp_path, fake=True)
    assert (tmp_path / "units" / "rtdms-pi-user.service").read_text() == UNIT.read_text()
    calls = _calls(tmp_path)
    assert "--user daemon-reload" in calls
    assert "--user enable --now rtdms-pi-user.service" in calls


def test_uninstall(tmp_path: Path) -> None:
    _run(tmp_path, fake=True)
    _run(tmp_path, "--uninstall", fake=True)
    assert not (tmp_path / "units" / "rtdms-pi-user.service").exists()
    calls = _calls(tmp_path)
    assert "--user disable --now rtdms-pi-user.service" in calls
    assert calls[-1] == "--user daemon-reload"


def test_open_flag_writes_dropin_and_default_removes_it(tmp_path: Path) -> None:
    dropin = tmp_path / "units" / "rtdms-pi-user.service.d" / "open.conf"
    _run(tmp_path, "--open", fake=True)
    assert dropin.read_text() == "[Service]\nEnvironment=RTDMS_BLE_OPEN=1\n"
    _run(tmp_path, fake=True)
    assert not dropin.exists()
    _run(tmp_path, "--open", fake=True)
    _run(tmp_path, "--uninstall", fake=True)
    assert not dropin.exists()


def test_unit_has_no_open_mode_by_default() -> None:
    assert "RTDMS_BLE_OPEN" not in UNIT.read_text()
