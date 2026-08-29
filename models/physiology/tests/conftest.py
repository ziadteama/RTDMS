"""Virtual-time helpers shared by the service tests.

``docs/VALIDATION.md`` forbids real sleeps and wall-clock deadlines in tests, so
the service's clock and its frame-wait primitive are both injected here. The
wait primitive advances the event loop with zero-delay yields and declares a
timeout once the loop has quiesced, which costs no wall-clock time at all.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Iterable, Sequence
from contextlib import suppress
from dataclasses import replace

from dms_physiology.simulate import synthetic_frames
from dms_physiology.types import PpgFrame, SensorStatus

QUIESCE_TURNS = 6


async def virtual_wait_for(
    awaitable: Awaitable[PpgFrame | None], timeout: float
) -> PpgFrame | None:
    """Resolve ``awaitable`` or raise ``TimeoutError`` without any real delay."""

    task = asyncio.ensure_future(awaitable)
    for _ in range(QUIESCE_TURNS):
        if task.done():
            break
        await asyncio.sleep(0)
    if not task.done():
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        raise TimeoutError(timeout)
    return task.result()


class FixedClock:
    """Monotonic clock stand-in returning a constant nanosecond reading."""

    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


def fixed_clock(value: int = 1_000_000_000) -> FixedClock:
    """Return a clock that never advances, so payloads are byte-comparable."""

    return FixedClock(value)


class ScriptedSource:
    """Yield frames, pausing for a bounded number of event-loop turns on an int.

    An integer in the script means "produce nothing for this many loop turns",
    which is how a silent BLE link is expressed without sleeping.
    """

    def __init__(self, script: Iterable[PpgFrame | int]) -> None:
        self._script = tuple(script)
        self.closed = False

    async def frames(self) -> AsyncIterator[PpgFrame]:
        try:
            for item in self._script:
                if isinstance(item, int):
                    for _ in range(item):
                        await asyncio.sleep(0)
                else:
                    yield item
        finally:
            self.closed = True


class HealthySource:
    """Replay source that also implements the optional ``health()`` protocol."""

    def __init__(self, frames: Sequence[PpgFrame], health: dict[str, int]) -> None:
        self._frames = tuple(frames)
        self._health = health

    def health(self) -> dict[str, int]:
        return self._health

    async def frames(self) -> AsyncIterator[PpgFrame]:
        for frame in self._frames:
            yield frame


def frames_with_gap(
    seconds: int, drop_from_frame: int, drop_frames: int
) -> tuple[PpgFrame, ...]:
    """Drop whole frames so the sample index really jumps, as a lost burst would."""

    frames = synthetic_frames(seconds)
    return frames[:drop_from_frame] + frames[drop_from_frame + drop_frames :]


def frames_with_reset(seconds_before: int, seconds_after: int) -> tuple[PpgFrame, ...]:
    """Concatenate two sessions, the second restarting its sample index at zero."""

    after = synthetic_frames(seconds_after)
    first = after[0]
    restarted = replace(first, packet=replace(first.packet, status=SensorStatus.SENSOR_RESET))
    return (*synthetic_frames(seconds_before), restarted, *after[1:])
