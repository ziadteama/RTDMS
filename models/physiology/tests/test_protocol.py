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


def test_tracker_mcu_reset_does_not_corrupt_sample_gap() -> None:
    """Verify MCU reset with index 0 returns sample_gap == 0 and increments session_id."""
    tracker = PacketTracker()
    samples_20 = tuple((i, i + 1) for i in range(20))
    p1 = make_packet(sequence=10, first_sample_index=360000, samples=samples_20)
    obs1 = tracker.observe(p1)
    assert obs1.session_id == 0

    p_reset = make_packet(
        sequence=11,
        first_sample_index=0,
        status=SensorStatus.SENSOR_RESET,
        samples=((1, 2),),
    )
    obs_reset = tracker.observe(p_reset)

    assert obs_reset.reset_detected
    assert obs_reset.sample_gap == 0
    assert obs_reset.sequence_gap == 0
    assert obs_reset.session_id == 1


def test_tracker_backwards_rollback_without_reset_returns_zero_sample_gap() -> None:
    """Verify index rollback without reset flag does not report sample_gap and updates state."""
    tracker = PacketTracker()
    samples_20 = tuple((i, i + 1) for i in range(20))
    p1 = make_packet(sequence=10, first_sample_index=100, samples=samples_20)
    assert tracker.observe(p1).session_id == 0

    p2 = make_packet(sequence=11, first_sample_index=50, samples=((1, 2),))
    obs2 = tracker.observe(p2)

    assert not obs2.reset_detected
    assert obs2.sample_gap == 0
    assert obs2.sequence_gap == 0
    assert obs2.session_id == 0

    p3 = make_packet(sequence=12, first_sample_index=51, samples=((1, 2),))
    obs3 = tracker.observe(p3)

    assert obs3.sample_gap == 0
    assert obs3.sequence_gap == 0


def test_tracker_detects_delayed_duplicates() -> None:
    """Verify that duplicates delivered late are correctly detected."""
    tracker = PacketTracker()
    p1 = make_packet(sequence=10, first_sample_index=100)
    p2 = make_packet(sequence=11, first_sample_index=102)
    p3 = make_packet(sequence=12, first_sample_index=104)

    assert not tracker.observe(p1).duplicate
    assert not tracker.observe(p2).duplicate
    assert not tracker.observe(p3).duplicate

    obs_dup = tracker.observe(p2)
    assert obs_dup.duplicate
    assert obs_dup.sample_gap == 0
    assert obs_dup.sequence_gap == 0
