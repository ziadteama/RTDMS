"""Factory label printer script.

Generates and prints Wi-Fi hotspot pairing QR string and ASCII QR code for
factory production labels.

NOTE: This script does NOT enforce a TTY check. Its output contains plain-text
secrets including the Wi-Fi PSK and the pairing token. Run only in secure
factory environments.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from rtdms_pi.pairing import (
    build_pairing,
    load_or_create_psk,
    load_or_create_token,
    render_qr_ascii,
    wifi_qr_string,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print Wi-Fi hotspot pairing QR string and ASCII QR code for factory labels."
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

    args = parser.parse_args(argv)

    token = load_or_create_token(args.state_dir / "token")
    psk = load_or_create_psk(args.psk_file)

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
