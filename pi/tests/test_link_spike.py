from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from link_spike.metrics import (  # noqa: E402
    build_csv_row,
    calculate_notify_loss,
    calculate_percentiles,
    decode_throttled,
    parse_garmin_loss,
)


def test_percentile_calculations() -> None:
    assert calculate_percentiles([]) == (0.0, 0.0)
    samples = [10.0, 20.0, 30.0, 40.0, 50.0]
    p50, p95 = calculate_percentiles(samples)
    assert p50 == 30.0
    assert p95 == 50.0

    samples100 = list(range(1, 101))
    p50_100, p95_100 = calculate_percentiles([float(x) for x in samples100])
    assert p50_100 == 50.0
    assert p95_100 == 95.0


def test_decode_throttled() -> None:
    assert decode_throttled("throttled=0x50005") == 0x50005
    assert decode_throttled("throttled=0x0\n") == 0
    assert decode_throttled("0x50005") == 0x50005
    assert decode_throttled("0") == 0
    assert decode_throttled("invalid") == 0


def test_build_csv_row() -> None:
    row = build_csv_row(
        timestamp=1732190000.5,
        uptime_s=3600,
        throttled=0x50005,
        temp_c=58.2,
        cpu_pct=42.5,
        fps=14.8,
        dmesg_errors=0,
    )
    assert row == "1732190000.5,3600,0x50005,58.2,42.5,14.8,0"


def test_calculate_notify_loss() -> None:
    # 60s at 5 Hz = 300 expected packets
    # If 300 received -> 0% loss
    assert calculate_notify_loss(300, 60.0, 5.0) == 0.0
    # If 270 received -> 30 lost = 10% loss
    assert calculate_notify_loss(270, 60.0, 5.0) == 10.0
    # If 0 duration
    assert calculate_notify_loss(10, 0.0, 5.0) == 0.0


def test_parse_garmin_loss() -> None:
    log_text = """
    Nov 21 19:00:00 rtdms systemd[1]: Stopping rtdms-pi.service...
    Nov 21 19:00:01 rtdms rtdms-pi[1234]: [garmin] received 1900, lost 100
    Nov 21 19:00:02 rtdms systemd[1]: Stopped rtdms-pi.service.
    """
    received, lost, loss_pct = parse_garmin_loss(log_text)
    assert received == 1900
    assert lost == 100
    assert loss_pct == 5.0

    with pytest.raises(ValueError):
        parse_garmin_loss("no matching lines here")
