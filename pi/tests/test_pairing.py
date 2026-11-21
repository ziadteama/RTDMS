from __future__ import annotations

import json
import stat
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from rtdms_pi.pairing import (
    build_pairing,
    load_or_create_token,
    main,
    render_qr_ascii,
    rotate_token,
    wifi_qr_string,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_token_persistence_mode_and_length(tmp_path: Path) -> None:
    token_path = tmp_path / "sub" / "token"
    token1 = load_or_create_token(token_path)

    # Token must have length >= 16
    assert len(token1) >= 16

    # File mode must be 0o600
    assert token_path.exists()
    mode = stat.S_IMODE(token_path.stat().st_mode)
    assert mode == 0o600

    # Persistence: subsequent load returns identical token
    token2 = load_or_create_token(token_path)
    assert token2 == token1


def test_build_pairing_schema_and_fixture() -> None:
    schema_path = REPO_ROOT / "contracts" / "pi-link" / "schemas" / "qr.schema.json"
    fixture_path = REPO_ROOT / "contracts" / "pi-link" / "fixtures" / "qr.json"

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    pairing = build_pairing(
        ssid=fixture["ssid"],
        psk=fixture["psk"],
        url=fixture["url"],
        ble=fixture["ble"],
        token=fixture["token"],
        contract=fixture["contract"],
    )

    # Validates against JSON Schema
    jsonschema.validate(instance=pairing, schema=schema)

    # Equals fixture values
    assert pairing == fixture


def test_wifi_qr_string_fixture() -> None:
    fixture_path = REPO_ROOT / "contracts" / "pi-link" / "fixtures" / "qr.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    expected = (
        "WIFI:T:WPA;S:RTDMS-Pi;P:example-passphrase;"
        "U:http://10.42.0.1:8080;B:RTDMS-Pi;K:k3Jx9mQ2pL7vN4wR8tY1;V:1;;"
    )
    assert wifi_qr_string(fixture) == expected


def test_wifi_qr_string_escaping() -> None:
    # Escaping test with semicolon in SSID and special characters in PSK
    p: dict[str, Any] = {
        "ssid": "My;SSID",
        "psk": 'pass"with;chars,and:colons\\and\\slashes',
        "url": "http://10.42.0.1:8080",
        "ble": "RTDMS-Pi",
        "token": "k3Jx9mQ2pL7vN4wR8tY1",
        "contract": 1,
    }
    s = wifi_qr_string(p)
    assert "S:My\\;SSID;" in s
    assert 'P:pass\\"with\\;chars\\,and\\:colons\\\\and\\\\slashes;' in s


def test_rotate_changes_token(tmp_path: Path) -> None:
    token_path = tmp_path / "token"
    token1 = load_or_create_token(token_path)
    token2 = rotate_token(token_path)

    assert token1 != token2
    assert len(token2) >= 16
    mode = stat.S_IMODE(token_path.stat().st_mode)
    assert mode == 0o600

    token3 = load_or_create_token(token_path)
    assert token3 == token2


def test_render_qr_ascii() -> None:
    text = "WIFI:T:WPA;S:Test;;"
    ascii_art = render_qr_ascii(text)
    assert len(ascii_art) > 0


def test_render_qr_ascii_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    orig_import = builtins.__import__

    def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "qrcode":
            raise ImportError("No module named 'qrcode'")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    monkeypatch.setitem(sys.modules, "qrcode", None)  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match=r"install rtdms-pi\[qr\]"):
        render_qr_ascii("WIFI:T:WPA;S:Test;;")


def test_main_cli_tty_protection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    psk_file = tmp_path / "wifi_psk"
    psk_file.write_text("testpassphrase123\n", encoding="utf-8")

    # Simulate non-TTY stdout without --force
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    exit_code = main(["--state-dir", str(tmp_path), "--psk-file", str(psk_file)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "refuse" in captured.err.lower() or "not a tty" in captured.err.lower()

    # With --force, outputs QR string
    exit_code = main(["--state-dir", str(tmp_path), "--psk-file", str(psk_file), "--force"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "WIFI:T:WPA;S:RTDMS-Pi;P:testpassphrase123;" in captured.out


def test_main_cli_rotate_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    psk_file = tmp_path / "wifi_psk"
    psk_file.write_text("testpassphrase123\n", encoding="utf-8")
    token_file = tmp_path / "token"
    token_file.write_text("initial_token_123456\n", encoding="utf-8")

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    exit_code = main(["--state-dir", str(tmp_path), "--psk-file", str(psk_file), "--rotate-token"])
    assert exit_code == 0
    new_token = token_file.read_text(encoding="utf-8").strip()
    assert new_token != "initial_token_123456"
    assert len(new_token) >= 16
    captured = capsys.readouterr()
    assert f"K:{new_token};" in captured.out
