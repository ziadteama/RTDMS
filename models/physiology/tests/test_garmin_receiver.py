"""The receiver's write path (no Bluetooth): Pi timestamps, drops, CSV log, frame queue."""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path

from dms_physiology.garmin_receiver import GarminRrReceiver, RrCsvLog
from dms_physiology.garmin_rr import Arrival, RrPacket, encode


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def packet(seq: int, rr: tuple[int, ...] = (850,)) -> bytes:
    return encode(RrPacket(seq=seq, watch_ms=1000 * seq, hr_bpm=70, rr_ms=rr))


def test_frames_carry_pi_time_and_duplicates_are_dropped(tmp_path: Path) -> None:
    clock = FakeClock()
    log = RrCsvLog(tmp_path / "rr.csv")
    rx = GarminRrReceiver(log, clock=clock, wall=lambda: 1_800_000_000.0 + clock.t)
    f1 = rx.handle_write(packet(1))
    clock.t += 1.0
    dup = rx.handle_write(packet(1))
    clock.t += 1.0
    f3 = rx.handle_write(packet(3))  # seq 2 lost
    log.close()

    assert f1 is not None and f1.rx_monotonic == 100.0 and f1.rx_wall == 1_800_000_100.0
    assert dup is None
    assert f3 is not None and f3.lost_before == 1 and f3.gap_before
    assert (rx.tracker.received, rx.tracker.duplicates, rx.tracker.lost) == (2, 1, 1)

    rows = list(csv.DictReader((tmp_path / "rr.csv").open(encoding="utf8")))
    assert [r["arrival"] for r in rows] == ["new", "duplicate", "new"]  # raw log keeps all
    assert rows[0]["rr_ms"] == "850"
    assert rows[2]["lost_before"] == "1"


def test_undecodable_bytes_are_logged_and_counted(tmp_path: Path) -> None:
    log = RrCsvLog(tmp_path / "rr.csv")
    rx = GarminRrReceiver(log)
    assert rx.handle_write(b"\x09\x00") is None
    log.close()
    assert rx.decode_errors == 1
    rows = list(csv.DictReader((tmp_path / "rr.csv").open(encoding="utf8")))
    assert rows[0]["arrival"].startswith("bad:")
    assert rows[0]["raw_hex"] == "0900"


def test_accepted_frames_reach_the_queue_in_order() -> None:
    async def scenario() -> list[int]:
        rx = GarminRrReceiver()
        for s in (1, 2, 2, 3):
            rx.handle_write(packet(s))
        out = []
        it = rx.frames().__aiter__()
        for _ in range(3):
            out.append((await it.__anext__()).packet.seq)
        return out

    assert asyncio.run(scenario()) == [1, 2, 3]


def test_staleness_follows_the_last_accepted_packet() -> None:
    clock = FakeClock()
    rx = GarminRrReceiver(clock=clock)
    assert rx.seconds_since_last_packet() is None
    rx.handle_write(packet(1))
    clock.t += 7.5
    assert rx.seconds_since_last_packet() == 7.5


def test_new_session_frame_is_passed_on() -> None:
    rx = GarminRrReceiver()
    for s in range(5):
        rx.handle_write(packet(s))
    f = rx.handle_write(encode(RrPacket(seq=0, watch_ms=60_000, hr_bpm=70, rr_ms=(900,))))
    assert f is not None and f.arrival == Arrival.NEW_SESSION
