"""Garmin RR packet codec and sequence rules, against hand-made bytes (docs/packet_format.md)."""

from __future__ import annotations

import pytest

from dms_physiology.garmin_rr import (
    Arrival,
    RrCodecError,
    RrFlags,
    RrPacket,
    SequenceTracker,
    decode,
    encode,
)

# The worked example in docs/packet_format.md: seq 7, watch_ms 1000, HR 73, RR 817 and 810 ms.
SPEC_EXAMPLE = bytes.fromhex("01 01 07 00 E8 03 00 00 49 02 31 03 2A 03")


def test_spec_example_decodes() -> None:
    p = decode(SPEC_EXAMPLE)
    assert p.version == 1
    assert p.seq == 7
    assert p.watch_ms == 1000
    assert p.hr_bpm == 73
    assert p.rr_ms == (817, 810)
    assert p.flags == RrFlags.HR_VALID


def test_spec_example_encodes_to_the_same_bytes() -> None:
    assert encode(RrPacket(seq=7, watch_ms=1000, hr_bpm=73, rr_ms=(817, 810))) == SPEC_EXAMPLE


def test_no_rr_and_no_valid_hr() -> None:
    # flags 0 (HR not valid), hr byte 0, rr_count 0: a 10-byte packet
    p = decode(bytes.fromhex("01 00 01 00 10 27 00 00 00 00"))
    assert p.hr_bpm is None
    assert p.rr_ms == ()
    assert p.watch_ms == 10000


def test_five_rr_is_exactly_20_bytes_and_split_flag_survives() -> None:
    p = RrPacket(seq=65535, watch_ms=0xFFFFFFFF, hr_bpm=180, rr_ms=(300, 333, 400, 500, 2000),
                 flags=RrFlags.SPLIT)
    raw = encode(p)
    assert len(raw) == 20
    assert decode(raw) == RrPacket(seq=65535, watch_ms=0xFFFFFFFF, hr_bpm=180,
                                   rr_ms=(300, 333, 400, 500, 2000),
                                   flags=RrFlags.HR_VALID | RrFlags.SPLIT)


@pytest.mark.parametrize("raw, why", [
    (b"", "empty"),
    (bytes.fromhex("01 01 07 00 E8 03 00 00 49"), "shorter than the header"),
    (bytes.fromhex("02 01 07 00 E8 03 00 00 49 00"), "unknown version"),
    (bytes.fromhex("01 01 07 00 E8 03 00 00 49 02 31 03"), "rr_count 2 but one RR"),
    (bytes.fromhex("01 01 07 00 E8 03 00 00 49 01 31 03 2A 03"), "rr_count 1 but two RR"),
    (bytes.fromhex("01 01 07 00 E8 03 00 00 49 06") + bytes(12), "rr_count over 5"),
    (bytes(21), "longer than 20 bytes"),
])
def test_bad_packets_are_rejected(raw: bytes, why: str) -> None:
    with pytest.raises(RrCodecError):
        decode(raw)


def test_encode_refuses_six_rr() -> None:
    with pytest.raises(RrCodecError):
        encode(RrPacket(seq=0, watch_ms=0, hr_bpm=60, rr_ms=(1000,) * 6))


# ---------------------------------------------------------------- sequence rules
def pkt(seq: int, watch_ms: int) -> RrPacket:
    return RrPacket(seq=seq, watch_ms=watch_ms, hr_bpm=70, rr_ms=(850,))


def test_in_order_stream_has_no_loss() -> None:
    t = SequenceTracker()
    arrivals = [t.accept(pkt(s, 1000 * s), s, 1e9 + s).arrival for s in range(5)]
    assert arrivals == [Arrival.NEW] * 5
    assert (t.received, t.lost, t.duplicates) == (5, 0, 0)
    assert t.loss_fraction() == 0.0


def test_duplicate_is_dropped_and_counted() -> None:
    t = SequenceTracker()
    t.accept(pkt(1, 1000), 0.0, 0.0)
    f = t.accept(pkt(1, 1000), 0.1, 0.1)
    assert f.arrival == Arrival.DUPLICATE
    assert (t.received, t.duplicates) == (1, 1)


def test_lost_packets_are_counted_and_mark_a_gap() -> None:
    t = SequenceTracker()
    t.accept(pkt(10, 10_000), 0.0, 0.0)
    f = t.accept(pkt(13, 13_000), 3.0, 3.0)  # 11 and 12 never arrived
    assert f.arrival == Arrival.NEW
    assert f.lost_before == 2
    assert f.gap_before
    assert t.loss_fraction() == pytest.approx(2 / 4)


def test_late_packet_is_dropped() -> None:
    t = SequenceTracker()
    t.accept(pkt(20, 20_000), 0.0, 0.0)
    f = t.accept(pkt(19, 19_000), 0.5, 0.5)
    assert f.arrival == Arrival.LATE
    assert t.late == 1


def test_seq_wraps_without_loss() -> None:
    t = SequenceTracker()
    t.accept(pkt(65535, 5_000), 0.0, 0.0)
    f = t.accept(pkt(0, 6_000), 1.0, 1.0)
    assert f.arrival == Arrival.NEW
    assert f.lost_before == 0
    assert not f.gap_before


def test_app_restart_starts_a_new_session_without_counting_loss() -> None:
    t = SequenceTracker()
    for s in range(50):
        t.accept(pkt(s, 1000 * s), s, s)
    f = t.accept(pkt(0, 120_000), 60.0, 60.0)  # watch clock kept running, seq back to 0
    assert f.arrival == Arrival.NEW_SESSION
    assert f.session == 2
    assert f.gap_before
    assert t.lost == 0


def test_watch_reboot_starts_a_new_session() -> None:
    t = SequenceTracker()
    t.accept(pkt(300, 900_000), 0.0, 0.0)
    f = t.accept(pkt(301, 2_000), 1.0, 1.0)  # watch_ms went back 898 s
    assert f.arrival == Arrival.NEW_SESSION


def test_slow_packet_marks_a_gap_without_loss() -> None:
    t = SequenceTracker()
    t.accept(pkt(1, 1_000), 0.0, 0.0)
    f = t.accept(pkt(2, 6_000), 5.0, 5.0)  # next in order, but 5 s of watch time later
    assert f.lost_before == 0
    assert f.gap_before


def test_pi_time_is_carried_not_watch_time() -> None:
    t = SequenceTracker()
    f = t.accept(pkt(1, 123_456), rx_monotonic=42.5, rx_wall=1_800_000_000.25)
    assert (f.rx_monotonic, f.rx_wall) == (42.5, 1_800_000_000.25)
