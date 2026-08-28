"""PPG frame sources for deterministic replay and production BLE acquisition."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from typing import Protocol

from .protocol import PacketCodec
from .types import PpgFrame


class SampleSource(Protocol):
    """An asynchronous source of timestamped PPG frames."""

    def frames(self) -> AsyncIterator[PpgFrame]:
        """Yield decoded PPG frames until the source is exhausted or stopped."""


class ReplaySource:
    """Replay pre-built frames deterministically, optionally at sample-clock pace."""

    def __init__(self, frames: Iterable[PpgFrame], *, realtime: bool = False) -> None:
        self._frames = tuple(frames)
        self._realtime = realtime

    async def frames(self) -> AsyncIterator[PpgFrame]:
        """Yield frames in input order without modifying their timestamps."""

        previous: PpgFrame | None = None
        for frame in self._frames:
            if self._realtime and previous is not None:
                delay = frame.received_at_seconds - previous.received_at_seconds
                if delay > 0:
                    await asyncio.sleep(delay)
            yield frame
            previous = frame


class BleakSampleSource:
    """Decode BLE notifications without importing Bleak for replay-only workflows."""

    def __init__(self, address: str, characteristic_uuid: str, sample_rate_hz: int) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        self._address = address
        self._characteristic_uuid = characteristic_uuid
        self._sample_rate_hz = sample_rate_hz

    async def frames(self) -> AsyncIterator[PpgFrame]:
        """Connect to the bracelet and yield decoded notification frames."""

        try:
            from bleak import BleakClient
        except ImportError as error:
            raise RuntimeError("Bleak is required only for live BLE acquisition") from error

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[float, bytes]] = asyncio.Queue()

        def on_notification(_: object, data: bytearray) -> None:
            queue.put_nowait((loop.time(), bytes(data)))

        async with BleakClient(self._address) as client:
            await client.start_notify(self._characteristic_uuid, on_notification)
            try:
                while True:
                    received_at_seconds, payload = await queue.get()
                    yield PpgFrame(
                        packet=PacketCodec.decode(payload),
                        sample_rate_hz=self._sample_rate_hz,
                        received_at_seconds=received_at_seconds,
                    )
            finally:
                await client.stop_notify(self._characteristic_uuid)
