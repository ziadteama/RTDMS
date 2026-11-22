from pathlib import Path

UNIT = Path(__file__).parents[1] / "deploy/systemd/rtdms-pi.service"


def test_low_priority_unit() -> None:
    lines = UNIT.read_text().splitlines()
    assert {"Nice=10", "CPUWeight=20", "IOSchedulingClass=idle"} <= set(lines)
    assert "Nice=-5" not in lines
