"""Minimal local output transports for DMS fusion."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Protocol


class OutputSink(Protocol):
    """Receives serialized physiology output without blocking acquisition."""

    async def publish(self, output: Mapping[str, object]) -> None: ...


class InMemorySink:
    """Test sink that retains a bounded record of published outputs."""

    def __init__(self) -> None:
        self.outputs: list[dict[str, object]] = []

    async def publish(self, output: Mapping[str, object]) -> None:
        self.outputs.append(dict(output))


class UnixDatagramSink:
    """Best-effort local datagram transport with message boundaries preserved."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._socket.setblocking(False)

    async def publish(self, output: Mapping[str, object]) -> None:
        payload = json.dumps(output, separators=(",", ":"), allow_nan=False).encode("utf-8")
        loop = asyncio.get_running_loop()
        await loop.sock_sendto(self._socket, payload, str(self._path))

    def close(self) -> None:
        self._socket.close()


class BoundedOutputSink:
    """Isolate acquisition from a slow, absent, or failing downstream sink.

    Publishing only ever enqueues. When the queue is full the newest output is
    dropped and counted, and every exception raised by the wrapped sink -- an
    unbound Unix socket, a serialization failure -- is counted rather than
    propagated back into the acquisition loop.
    """

    def __init__(self, sink: OutputSink, *, maxsize: int = 64) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self._sink = sink
        self._queue: asyncio.Queue[Mapping[str, object]] = asyncio.Queue(maxsize=maxsize)
        self._writer: asyncio.Task[None] | None = None
        self.dropped_outputs = 0
        self.sink_errors = 0

    @property
    def queue_depth(self) -> int:
        """Return the number of outputs still waiting to reach the wrapped sink."""

        return self._queue.qsize()

    async def publish(self, output: Mapping[str, object]) -> None:
        """Enqueue one output, dropping and counting it when the queue is full."""

        if self._writer is None or self._writer.done():
            self._writer = asyncio.create_task(self._write_forever())
        try:
            self._queue.put_nowait(output)
        except asyncio.QueueFull:
            self.dropped_outputs += 1

    async def aclose(self) -> None:
        """Stop the writer task; queued outputs are abandoned."""

        writer = self._writer
        self._writer = None
        if writer is None:
            return
        writer.cancel()
        with suppress(asyncio.CancelledError):
            await writer

    async def _write_forever(self) -> None:
        while True:
            output = await self._queue.get()
            try:
                await self._sink.publish(output)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.sink_errors += 1
            finally:
                self._queue.task_done()
