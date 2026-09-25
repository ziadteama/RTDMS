"""Minimal local output transports for DMS fusion (mirrors physiology)."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol


class OutputSink(Protocol):
    async def publish(self, output: Mapping[str, object]) -> None: ...


class InMemorySink:
    def __init__(self) -> None:
        self.outputs: list[dict[str, object]] = []

    async def publish(self, output: Mapping[str, object]) -> None:
        self.outputs.append(dict(output))


class UnixDatagramSink:
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
    """Drop newest when fusion is slow — never stall the vision loop."""

    def __init__(self, sink: OutputSink, *, maxsize: int = 16) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self._sink = sink
        self._queue: asyncio.Queue[Mapping[str, object]] = asyncio.Queue(maxsize=maxsize)
        self._writer: asyncio.Task[None] | None = None
        self.dropped_outputs = 0
        self.sink_errors = 0

    async def publish(self, output: Mapping[str, object]) -> None:
        if self._writer is None or self._writer.done():
            self._writer = asyncio.create_task(self._write_forever())
        try:
            self._queue.put_nowait(output)
        except asyncio.QueueFull:
            self.dropped_outputs += 1

    async def _write_forever(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                await self._sink.publish(item)
            except Exception:
                self.sink_errors += 1

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.cancel()
            try:
                await self._writer
            except asyncio.CancelledError:
                pass
