from __future__ import annotations

import pytest

from dms_physiology.protocol import PACKET_VERSION, PacketCodec, PacketCodecError, PacketTracker
from dms_physiology.types import Channel, PpgPacket, SensorStatus

MAX_VALUE = (1 << 18) - 1


def make_packet(
    *,
    sequence: int = 12,
    first_sample_index: int = 100,
    status: SensorStatus = SensorStatus.NONE,
    samples: tuple[tuple[int, ...], ...] = ((1, 2), (MAX_VALUE, 5)),
) -> PpgPacket:
    return PpgPacket(
        version=PACKET_VERSION,
        sequence=sequence,
        first_sample_index=first_sample_index,
        channels=Channel.RED | Channel.INFRARED,
        status=status,
        samples=samples,
    )


def test_packet_round_trip_preserves_all_wire_fields() -> None:
    packet = make_packet(status=SensorStatus.FIFO_OVERFLOW | SensorStatus.SATURATED)

    assert PacketCodec.decode(PacketCodec.encode(packet)) == packet


def test_codec_rejects_invalid_payload_length() -> None:
    payload = PacketCodec.encode(make_packet())[:-1]

    with pytest.raises(PacketCodecError, match="does not match expected"):
        PacketCodec.decode(payload)


def test_codec_rejects_unknown_version_and_invalid_sample_value() -> None:
    invalid_version = PpgPacket(
        version=99,
        sequence=0,
        first_sample_index=0,
        channels=Channel.RED,
        status=SensorStatus.NONE,
        samples=((1,),),
    )
    invalid_value = PpgPacket(
        version=PACKET_VERSION,
        sequence=0,
        first_sample_index=0,
        channels=Channel.RED,
        status=SensorStatus.NONE,
        samples=((MAX_VALUE + 1,),),
    )

    with pytest.raises(PacketCodecError, match="unsupported"):
        PacketCodec.encode(invalid_version)
    with pytest.raises(PacketCodecError, match="18-bit"):
        PacketCodec.encode(invalid_value)


def test_tracker_reports_packet_and_sample_gaps() -> None:
    tracker = PacketTracker()
    tracker.observe(make_packet(sequence=65535, first_sample_index=10, samples=((1, 2), (3, 4))))

    observation = tracker.observe(make_packet(sequence=1, first_sample_index=15, samples=((5, 6),)))

    assert observation.sequence_gap == 1
    assert observation.sample_gap == 3
    assert not observation.duplicate
    assert not observation.reordered


def test_tracker_detects_duplicate_reordering_and_sensor_reset() -> None:
    tracker = PacketTracker()
    first = make_packet(sequence=8, first_sample_index=100, samples=((1, 2),))
    tracker.observe(first)

    duplicate = tracker.observe(first)
    reordered = tracker.observe(make_packet(sequence=7, first_sample_index=99, samples=((1, 2),)))
    reset = tracker.observe(
        make_packet(
            sequence=9, first_sample_index=0, status=SensorStatus.SENSOR_RESET, samples=((1, 2),)
        )
    )

    assert duplicate.duplicate
    assert reordered.reordered
    assert reset.reset_detected


def test_tracker_keeps_last_accepted_packet_after_reordering() -> None:
    tracker = PacketTracker()
    tracker.observe(make_packet(sequence=8, first_sample_index=100, samples=((1, 2),)))
    tracker.observe(make_packet(sequence=7, first_sample_index=99, samples=((1, 2),)))

    observation = tracker.observe(
        make_packet(sequence=9, first_sample_index=101, samples=((1, 2),))
    )

    assert observation.sequence_gap == 0
    assert observation.sample_gap == 0
