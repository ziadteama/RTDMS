"""Minimal local output transports for DMS fusion."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Mapping
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
