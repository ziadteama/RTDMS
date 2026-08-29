import asyncio
import struct

import pytest

from dms_physiology.acquisition import SocketSampleSource
from dms_physiology.protocol import PACKET_VERSION, PacketCodec
from dms_physiology.types import Channel, PpgPacket, SensorStatus


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def make_packet(sequence: int, first_sample_index: int) -> PpgPacket:
    return PpgPacket(
        version=PACKET_VERSION,
        sequence=sequence,
        first_sample_index=first_sample_index,
        channels=Channel.RED | Channel.INFRARED,
        status=SensorStatus.CONTACT_LOST,
        samples=((1, 2), ((1 << 18) - 1, 0)),
    )


async def test_socket_source_reads_length_prefixed_packets():
    packet = make_packet(1, 100)
    payload = PacketCodec.encode(packet)
    length_prefix = struct.pack("!H", len(payload))
    
    port = None

    async def handle_client(reader, writer):
        writer.write(length_prefix + payload)
        await writer.drain()
        writer.close()
        import contextlib
        with contextlib.suppress(Exception):
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    
    source = SocketSampleSource('127.0.0.1', port, 125)
    stream = source.frames()
    
    frame = await anext(stream)
    assert frame.packet.sequence == 1
    
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
        
    server.close()
    import contextlib
    with contextlib.suppress(Exception):
        await server.wait_closed()


async def test_socket_source_health():
    packet = make_packet(1, 100)
    payload = PacketCodec.encode(packet)
    length_prefix = struct.pack("!H", len(payload))
    
    async def handle_client(reader, writer):
        writer.write(length_prefix + payload)
        await writer.drain()
        writer.close()
        import contextlib
        with contextlib.suppress(Exception):
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    
    source = SocketSampleSource('127.0.0.1', port, 125)
    stream = source.frames()
    
    await anext(stream)
    health = source.health()
    assert health["packets_received"] == 1
    
    server.close()
    import contextlib
    with contextlib.suppress(Exception):
        await server.wait_closed()
