"""The step-1 tool's Heart Rate Measurement parser, against hand-made notifications."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent / "tools" / "check_garmin_broadcast.py"
spec = importlib.util.spec_from_file_location("check_garmin_broadcast", TOOL)
assert spec is not None and spec.loader is not None
tool = importlib.util.module_from_spec(spec)
sys.modules["check_garmin_broadcast"] = tool
spec.loader.exec_module(tool)


def test_hr_only_8bit() -> None:
    # flags 0x00: 8-bit HR, no contact info, no energy, no RR; HR 72
    m = tool.parse_hr_measurement(bytes([0x00, 72]))
    assert m.heart_rate_bpm == 72
    assert m.rr_ms == []
    assert m.energy_kj is None


def test_contact_bits_do_not_change_layout() -> None:
    # flags 0x06: contact supported + detected; HR 65
    m = tool.parse_hr_measurement(bytes([0x06, 65]))
    assert m.heart_rate_bpm == 65
    assert m.rr_ms == []


def test_rr_intervals_in_1024ths_of_a_second() -> None:
    # flags 0x10: RR present; HR 60; RR 1024/1024 s = 1000 ms and 768/1024 s = 750 ms
    data = bytes([0x10, 60]) + (1024).to_bytes(2, "little") + (768).to_bytes(2, "little")
    m = tool.parse_hr_measurement(data)
    assert m.heart_rate_bpm == 60
    assert m.rr_ms == pytest.approx([1000.0, 750.0])


def test_16bit_hr_energy_and_rr() -> None:
    # flags 0x19: 16-bit HR + energy + RR; HR 300 (exercises the 2-byte field); energy 5 kJ
    data = (bytes([0x19]) + (300).to_bytes(2, "little") + (5).to_bytes(2, "little")
            + (512).to_bytes(2, "little"))
    m = tool.parse_hr_measurement(data)
    assert m.heart_rate_bpm == 300
    assert m.energy_kj == 5
    assert m.rr_ms == pytest.approx([500.0])


@pytest.mark.parametrize("data", [b"", bytes([0x00]), bytes([0x01, 70]),
                                  bytes([0x10, 70, 0x00])])
def test_malformed_packets_raise(data: bytes) -> None:
    with pytest.raises(ValueError):
        tool.parse_hr_measurement(data)
