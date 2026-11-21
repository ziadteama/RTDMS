from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_UP = REPO_ROOT / "pi" / "deploy" / "hotspot" / "rtdms-ap-up.sh"
SCRIPT_DOWN = REPO_ROOT / "pi" / "deploy" / "hotspot" / "rtdms-ap-down.sh"


def test_hotspot_up_dry_run(tmp_path: Path) -> None:
    psk_file = tmp_path / "wifi_psk"
    env = os.environ.copy()
    env["RTDMS_PSK_FILE"] = str(psk_file)

    res = subprocess.run(
        [str(SCRIPT_UP), "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    stdout = res.stdout
    assert "band a" in stdout
    assert "36" in stdout
    assert "autoconnect no" in stdout

    # PSK file should be created with mode 0o600
    assert psk_file.exists()
    mode = stat.S_IMODE(psk_file.stat().st_mode)
    assert mode == 0o600

    psk = psk_file.read_text(encoding="utf-8").strip()
    assert len(psk) > 0
    # stdout must never contain the PSK text
    assert psk not in stdout


def test_hotspot_up_dfs_channel_fails(tmp_path: Path) -> None:
    psk_file = tmp_path / "wifi_psk"
    env = os.environ.copy()
    env["RTDMS_PSK_FILE"] = str(psk_file)
    env["RTDMS_WIFI_CHANNEL"] = "100"

    res = subprocess.run(
        [str(SCRIPT_UP), "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert res.returncode != 0
    assert "DFS" in res.stderr or "DFS" in res.stdout


def test_hotspot_down_dry_run() -> None:
    res = subprocess.run(
        [str(SCRIPT_DOWN), "--dry-run"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "nmcli con down rtdms-ap" in res.stdout
    assert "nmcli radio wifi off" in res.stdout
