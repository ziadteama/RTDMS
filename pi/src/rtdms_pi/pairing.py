"""Wi-Fi hotspot pairing and QR generation for the RTDMS Pi runtime."""

from __future__ import annotations

import argparse
import io
import os
import secrets
import sys
from pathlib import Path
from typing import Any


def load_or_create_token(path: Path) -> str:
    """Load existing pairing token or create a new random urlsafe token with mode 0o600.

    The token is at least 16 characters long and is never logged.
    """
    if path.exists() and path.is_file():
        token = path.read_text(encoding="utf-8").strip()
        if len(token) >= 16:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            return token

    return rotate_token(path)


def rotate_token(path: Path) -> str:
    """Regenerate pairing token with mode 0o600, invalidating previous pairings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(18)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"{token}\n")
    os.chmod(path, 0o600)
    return token


def load_or_create_psk(path: Path) -> str:
    """Load existing Wi-Fi PSK or generate a random one and save with mode 0o600."""
    if path.exists() and path.is_file():
        psk = path.read_text(encoding="utf-8").strip()
        if psk:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            return psk

    path.parent.mkdir(parents=True, exist_ok=True)
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    psk = "".join(secrets.choice(alphabet) for _ in range(24))
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"{psk}\n")
    os.chmod(path, 0o600)
    return psk


def build_pairing(
    ssid: str,
    psk: str,
    url: str,
    ble: str,
    token: str,
    contract: int = 1,
) -> dict[str, Any]:
    """Build pairing dictionary matching contracts/pi-link/schemas/qr.schema.json."""
    return {
        "ssid": ssid,
        "psk": psk,
        "url": url,
        "ble": ble,
        "token": token,
        "contract": contract,
    }


def _escape_wifi_value(val: str) -> str:
    r"""Standard Wi-Fi QR escaping of \ ; , : " in values."""
    val = val.replace("\\", "\\\\")
    for ch in (";", ",", ":", '"'):
        val = val.replace(ch, f"\\{ch}")
    return val


def _escape_url_value(val: str) -> str:
    r"""Escape backslash and semicolon in URL field to preserve field delimiters."""
    val = val.replace("\\", "\\\\")
    val = val.replace(";", "\\;")
    return val


def wifi_qr_string(p: dict[str, Any]) -> str:
    """Generate Wi-Fi QR pairing string matching contract specification."""
    ssid = _escape_wifi_value(str(p["ssid"]))
    psk = _escape_wifi_value(str(p["psk"]))
    url = _escape_url_value(str(p["url"]))
    ble = _escape_wifi_value(str(p["ble"]))
    token = _escape_wifi_value(str(p["token"]))
    contract = int(p["contract"])
    return f"WIFI:T:WPA;S:{ssid};P:{psk};U:{url};B:{ble};K:{token};V:{contract};;"


def render_qr_ascii(text: str) -> str:
    """Render QR code as ASCII art string.

    Requires qrcode library (lazy import).
    Raises RuntimeError("install rtdms-pi[qr]") if not installed.
    """
    try:
        import qrcode
    except ImportError as exc:
        raise RuntimeError("install rtdms-pi[qr]") from exc

    qr: Any = qrcode.QRCode()  # qrcode ships no type hints
    qr.add_data(text)
    qr.make(fit=True)
    buf = io.StringIO()
    qr.print_ascii(out=buf)
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for rtdms-pair."""
    parser = argparse.ArgumentParser(
        prog="rtdms-pair",
        description="Print Wi-Fi hotspot pairing QR string and ASCII QR code.",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path(os.getenv("STATE_DIRECTORY", "/var/lib/rtdms")),
        help="Directory storing pairing state and tokens (default: /var/lib/rtdms)",
    )
    parser.add_argument(
        "--ssid",
        default=os.getenv("RTDMS_SSID", "RTDMS-Pi"),
        help="Wi-Fi SSID (default: RTDMS-Pi)",
    )
    parser.add_argument(
        "--psk-file",
        type=Path,
        default=Path(os.getenv("RTDMS_PSK_FILE", "/var/lib/rtdms/wifi_psk")),
        help="Path to file containing Wi-Fi PSK (default: /var/lib/rtdms/wifi_psk)",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("RTDMS_URL", "http://10.42.0.1:8080"),
        help="HTTP base URL (default: http://10.42.0.1:8080)",
    )
    parser.add_argument(
        "--ble",
        default=os.getenv("RTDMS_BLE_NAME", "RTDMS-Pi"),
        help="BLE device name (default: RTDMS-Pi)",
    )
    parser.add_argument(
        "--rotate-token",
        action="store_true",
        help="Regenerate the pairing token (unpairs every phone)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force printing PSK/token even if stdout is not a TTY",
    )

    args = parser.parse_args(argv)

    if not sys.stdout.isatty() and not args.force:
        sys.stderr.write("Error: stdout is not a TTY. Use --force to print secrets.\n")
        return 1

    token_path = args.state_dir / "token"
    if args.rotate_token:
        token = rotate_token(token_path)
    else:
        token = load_or_create_token(token_path)

    if args.psk_file.exists() and args.psk_file.is_file():
        psk = args.psk_file.read_text(encoding="utf-8").strip()
    else:
        try:
            psk = load_or_create_psk(args.psk_file)
        except Exception:
            sys.stderr.write(f"Error: PSK file not found or cannot be created: {args.psk_file}\n")
            return 1

    pairing = build_pairing(
        ssid=args.ssid,
        psk=psk,
        url=args.url,
        ble=args.ble,
        token=token,
    )

    qr_str = wifi_qr_string(pairing)
    print(qr_str)

    try:
        ascii_qr = render_qr_ascii(qr_str)
        sys.stdout.write(ascii_qr)
    except RuntimeError:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
