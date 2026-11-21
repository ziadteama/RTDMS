from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from unittest.mock import patch

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
spec = importlib.util.spec_from_file_location("factory_label", TOOLS_DIR / "factory_label.py")
assert spec is not None and spec.loader is not None
factory_label = importlib.util.module_from_spec(spec)
spec.loader.exec_module(factory_label)


def test_factory_label_prints_secrets_without_tty(tmp_path: Path) -> None:
    psk_file = tmp_path / "wifi_psk"
    token_file = tmp_path / "token"
    token_file.write_text("test-secret-token-1234\n", encoding="utf-8")
    psk_file.write_text("test-wifi-psk-5678\n", encoding="utf-8")

    buf = io.StringIO()
    argv = [
        "--state-dir",
        str(tmp_path),
        "--psk-file",
        str(psk_file),
        "--ssid",
        "Factory-SSID",
        "--url",
        "http://10.42.0.1:8080",
        "--ble",
        "Factory-BLE",
    ]

    with patch("sys.stdout", buf):
        exit_code = factory_label.main(argv)

    assert exit_code == 0
    output = buf.getvalue()
    # Verifies output contains the QR string with ssid and secrets
    assert "WIFI:T:WPA;S:Factory-SSID;P:test-wifi-psk-5678;" in output
    assert ";B:Factory-BLE;K:test-secret-token-1234;V:1;;" in output
