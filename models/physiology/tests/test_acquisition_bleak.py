from __future__ import annotations

import sys
from collections.abc import AsyncGenerator, Callable, Sequence
from types import ModuleType

import pytest

from dms_physiology.acquisition import BleakSampleSource
from dms_physiology.protocol import PACKET_VERSION, PacketCodec
from dms_physiology.types import Channel, PpgFrame, PpgPacket, SensorStatus

ADDRESS = "AA:BB:CC:DD:EE:FF"
CHARACTERISTIC_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
SAMPLE_RATE_HZ = 125


def make_packet(sequence: int, first_sample_index: int) -> PpgPacket:
    return PpgPacket(
        version=PACKET_VERSION,
        sequence=sequence,
        first_sample_index=first_sample_index,
        channels=Channel.RED | Channel.INFRARED,
        status=SensorStatus.CONTACT_LOST,
        samples=((1, 2), ((1 << 18) - 1, 0)),
    )


class FakeBleakClient:
    """Stand in for ``bleak.BleakClient`` with a scripted notification burst."""

    def __init__(self, address: str, payloads: Sequence[bytes]) -> None:
        self.address = address
        self.payloads = payloads
        self.started: list[str] = []
        self.stopped: list[str] = []

    async def __aenter__(self) -> FakeBleakClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def start_notify(
        self, characteristic_uuid: str, callback: Callable[[object, bytearray], None]
    ) -> None:
        self.started.append(characteristic_uuid)
        for payload in self.payloads:
            callback(object(), bytearray(payload))

    async def stop_notify(self, characteristic_uuid: str) -> None:
        self.stopped.append(characteristic_uuid)


def install_fake_bleak(
    monkeypatch: pytest.MonkeyPatch, payloads: Sequence[bytes]
) -> list[FakeBleakClient]:
    """Make ``from bleak import BleakClient`` resolve to a scripted fake."""

    clients: list[FakeBleakClient] = []

    def build_client(address: str) -> FakeBleakClient:
        client = FakeBleakClient(address, payloads)
        clients.append(client)
        return client

    module = ModuleType("bleak")
    module.BleakClient = build_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bleak", module)
    return clients


def open_stream() -> AsyncGenerator[PpgFrame, None]:
    source = BleakSampleSource(ADDRESS, CHARACTERISTIC_UUID, SAMPLE_RATE_HZ)
    stream: AsyncGenerator[PpgFrame, None] = source.frames()  # type: ignore[assignment]
    return stream


async def take(stream: AsyncGenerator[PpgFrame, None], count: int) -> list[PpgFrame]:
    """Consume exactly ``count`` frames, then shut the generator down."""

    collected = [await anext(stream) for _ in range(count)]
    await stream.aclose()
    return collected


async def test_notification_stream_round_trips_packets(monkeypatch: pytest.MonkeyPatch) -> None:
    packets = [make_packet(sequence=7, first_sample_index=100), make_packet(8, 102)]
    clients = install_fake_bleak(monkeypatch, [PacketCodec.encode(p) for p in packets])

    frames = await take(open_stream(), 2)

    assert [frame.packet for frame in frames] == packets
    assert [frame.sample_rate_hz for frame in frames] == [SAMPLE_RATE_HZ, SAMPLE_RATE_HZ]
    assert frames[0].received_at_seconds <= frames[1].received_at_seconds
    assert clients[0].address == ADDRESS
    assert clients[0].started == [CHARACTERISTIC_UUID]


async def test_malformed_notification_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    good = PacketCodec.encode(make_packet(1, 0))
    install_fake_bleak(monkeypatch, [b"\x01\x02\x03", good])
    source = BleakSampleSource(ADDRESS, CHARACTERISTIC_UUID, SAMPLE_RATE_HZ)
    stream = source.frames()

    frame = await anext(stream)

    assert frame.packet.sequence == 1
    assert source.health()["decode_errors"] == 1
    assert source.health()["packets_received"] == 2

    await stream.aclose()


async def test_disconnect_mid_stream_stops_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    payloads = [PacketCodec.encode(make_packet(index, index * 2)) for index in range(3)]
    clients = install_fake_bleak(monkeypatch, payloads)
    stream = open_stream()

    frames = await take(stream, 1)

    assert len(frames) == 1
    assert clients[0].stopped == [CHARACTERISTIC_UUID]
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


async def test_fast_notifications_drop_packets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = [PacketCodec.encode(make_packet(index, index * 2)) for index in range(70)]
    install_fake_bleak(monkeypatch, payloads)
    source = BleakSampleSource(ADDRESS, CHARACTERISTIC_UUID, SAMPLE_RATE_HZ)
    stream = source.frames()

    await anext(stream)
    health = source.health()

    assert health["queue_high_water"] == 64
    assert health["dropped_frames"] == 6
    assert health["packets_received"] == 70

    await stream.aclose()


async def test_missing_bleak_reports_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "bleak", None)

    with pytest.raises(RuntimeError, match="Bleak is required"):
        await anext(open_stream())
