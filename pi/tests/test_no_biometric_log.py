from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import Clock
from dms_physiology.garmin_rr import RrPacket, encode
from test_payloads import validate

from rtdms_pi.buzzer import PatternPlayer, RecordingBuzzer
from rtdms_pi.payloads import physio_payload
from rtdms_pi.runtime import Runtime
from rtdms_pi.sources import GarminPhysioSource, ScriptedFrameSource
from rtdms_pi.state import RuntimeState


def test_receiver_no_log_and_no_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    source = GarminPhysioSource(clock=clock, wall=lambda: 1234.0)
    assert source.latest() is None
    packet = encode(RrPacket(1, 1000, 75, (800, 810)))
    # Guard all Python file writes, not just files that survive until shutdown.
    import builtins
    import io
    import os

    original_open, original_io_open, original_os_open = builtins.open, io.open, os.open

    def guarded_open(file: object, mode: str = "r", *args: object, **kwargs: object) -> object:
        assert not any(c in mode for c in "wax+"), f"unexpected write: {file}"
        return original_open(file, mode, *args, **kwargs)

    def guarded_io(file: object, mode: str = "r", *args: object, **kwargs: object) -> object:
        assert not any(c in mode for c in "wax+"), f"unexpected write: {file}"
        return original_io_open(file, mode, *args, **kwargs)

    def guarded_os(file: object, flags: int, *args: object, **kwargs: object) -> int:
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        return original_os_open(file, flags, *args, **kwargs)

    with (
        patch("builtins.open", guarded_open),
        patch("io.open", guarded_io),
        patch("os.open", guarded_os),
    ):
        source.handle_write(b"bad")
        assert source.latest() is None

        # P3 will call handle_write from an active event loop.
        async def feed() -> None:
            source.handle_write(packet)

        asyncio.run(feed())
        report = source.latest()
        assert report is not None and report.raw["hr_bpm"] == 75
        assert "fatigue_probability" not in report.raw
        for seq in range(2, 300):
            source.handle_write(encode(RrPacket(seq, seq * 1000, 75, (800,))))
        assert source.tracker.received == 299
        assert source.decode_errors == 1
        state = RuntimeState(clock=clock)
        runtime = Runtime(
            ScriptedFrameSource([]), source, PatternPlayer(RecordingBuzzer()), state, clock
        )
        runtime.start()
        runtime.tick()
        payload = physio_payload(state.snapshot(), state.phone_clock)
        runtime.stop()
        clock.advance(10.01)
        assert source.latest() is None
    validate("physio", payload)
    assert list(tmp_path.iterdir()) == []
