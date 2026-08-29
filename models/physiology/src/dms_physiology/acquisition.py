"""PPG frame sources for deterministic replay and production BLE acquisition."""

from __future__ import annotations

import asyncio
import struct
from collections.abc import AsyncIterator, Iterable, Mapping
from typing import Protocol

from .protocol import PacketCodec, PacketCodecError
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


class _FramePump:
    """A shared pump managing a bounded queue and decode guard."""

    def __init__(self, sample_rate_hz: int, max_queue_size: int = 64) -> None:
        self._sample_rate_hz = sample_rate_hz
        self._queue: asyncio.Queue[
            tuple[float, bytes] | None
        ] = asyncio.Queue(maxsize=max_queue_size)
        self._packets_received = 0
        self._decode_errors = 0
        self._queue_high_water = 0
        self._dropped_frames = 0

    def put_nowait(self, received_at_seconds: float, payload: bytes) -> None:
        self._packets_received += 1
        if self._queue.full():
            self._dropped_frames += 1
        else:
            self._queue.put_nowait((received_at_seconds, payload))
            size = self._queue.qsize()
            if size > self._queue_high_water:
                self._queue_high_water = size

    async def put_eof(self) -> None:
        await self._queue.put(None)

    async def frames(self) -> AsyncIterator[PpgFrame]:
        while True:
            item = await self._queue.get()
            if item is None:
                break
            received_at_seconds, payload = item
            try:
                packet = PacketCodec.decode(payload)
            except PacketCodecError:
                self._decode_errors += 1
                continue
            
            yield PpgFrame(
                packet=packet,
                sample_rate_hz=self._sample_rate_hz,
                received_at_seconds=received_at_seconds,
            )

    def health(self) -> Mapping[str, int]:
        return {
            "packets_received": self._packets_received,
            "decode_errors": self._decode_errors,
            "queue_depth": self._queue.qsize(),
            "queue_high_water": self._queue_high_water,
            "dropped_frames": self._dropped_frames,
        }


class BleakSampleSource:
    """Decode BLE notifications without importing Bleak for replay-only workflows."""

    def __init__(self, address: str, characteristic_uuid: str, sample_rate_hz: int) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        self._address = address
        self._characteristic_uuid = characteristic_uuid
        self._pump = _FramePump(sample_rate_hz, max_queue_size=64)

    def health(self) -> Mapping[str, int]:
        return self._pump.health()

    async def frames(self) -> AsyncIterator[PpgFrame]:
        """Connect to the bracelet and yield decoded notification frames."""

        try:
            from bleak import BleakClient
        except ImportError as error:
            raise RuntimeError("Bleak is required only for live BLE acquisition") from error

        loop = asyncio.get_running_loop()

        def on_notification(_: object, data: bytearray) -> None:
            self._pump.put_nowait(loop.time(), bytes(data))

        async with BleakClient(self._address) as client:
            await client.start_notify(self._characteristic_uuid, on_notification)
            try:
                async for frame in self._pump.frames():
                    yield frame
            finally:
                await client.stop_notify(self._characteristic_uuid)


class SocketSampleSource:
    """Read wire-format length-delimited packets from a TCP socket."""

    def __init__(self, host: str, port: int, sample_rate_hz: int) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        self._host = host
        self._port = port
        self._pump = _FramePump(sample_rate_hz, max_queue_size=64)

    def health(self) -> Mapping[str, int]:
        return self._pump.health()

    async def frames(self) -> AsyncIterator[PpgFrame]:
        reader, writer = await asyncio.open_connection(self._host, self._port)
        loop = asyncio.get_running_loop()

        async def read_loop() -> None:
            try:
                while True:
                    length_prefix = await reader.readexactly(2)
                    length = struct.unpack("!H", length_prefix)[0]
                    payload = await reader.readexactly(length)
                    self._pump.put_nowait(loop.time(), payload)
            except (asyncio.IncompleteReadError, ConnectionError):
                pass
            finally:
                await self._pump.put_eof()
                writer.close()
                import contextlib
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

        reader_task = asyncio.create_task(read_loop())
        try:
            async for frame in self._pump.frames():
                yield frame
        finally:
            reader_task.cancel()
            import contextlib
            with contextlib.suppress(asyncio.CancelledError):
                await reader_task
