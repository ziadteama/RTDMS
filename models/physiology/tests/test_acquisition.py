from __future__ import annotations

import pytest

from dms_physiology.acquisition import ReplaySource
from dms_physiology.protocol import PACKET_VERSION
from dms_physiology.types import Channel, PpgFrame, PpgPacket, SensorStatus


def make_frame(index: int, received_at_seconds: float) -> PpgFrame:
    return PpgFrame(
        packet=PpgPacket(
            version=PACKET_VERSION,
            sequence=index,
            first_sample_index=index,
            channels=Channel.INFRARED,
            status=SensorStatus.NONE,
            samples=((index,),),
        ),
        sample_rate_hz=100,
        received_at_seconds=received_at_seconds,
    )


@pytest.mark.asyncio
async def test_replay_source_yields_original_frames_in_order() -> None:
    expected = (make_frame(1, 1.0), make_frame(2, 1.5))
    source = ReplaySource(expected)

    actual = tuple([frame async for frame in source.frames()])

    assert actual == expected


@pytest.mark.asyncio
async def test_replay_source_is_repeatable() -> None:
    source = ReplaySource((make_frame(1, 1.0),))

    first = tuple([frame async for frame in source.frames()])
    second = tuple([frame async for frame in source.frames()])

    assert first == second
