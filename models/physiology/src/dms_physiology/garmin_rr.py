"""Garmin watch RR packets: binary codec and sequence tracking (docs/packet_format.md).

The Connect IQ app on the watch sends one small packet per ~1 s batch of beat-to-beat (RR)
intervals. This module only turns bytes into checked values and decides, per packet, whether it
is new, a duplicate, late, or the start of a new session. It does no signal processing.

Timestamps: the Pi stamps every packet on arrival (`rx_monotonic`, `rx_wall`). The watch's own
`watch_ms` and `seq` are used only for ordering, loss counting and gap detection.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntFlag, StrEnum

PACKET_VERSION = 1
# The service UUID is 16-bit on purpose: Garmin watches only report scan results from devices
# that advertise a 16-bit service UUID (in General Discoverable mode); a device advertising only
# a 128-bit UUID never appears in Connect IQ scans. 0xFFF0 is a common vendor-test value, not an
# assigned service, so the characteristic keeps a unique 128-bit UUID: the watch only accepts a
# device whose FFF0 service has exactly this characteristic.
SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "1375193a-7edb-4a34-b3f2-18130239c8a8"
MAX_RR_PER_PACKET = 5  # 10-byte header + 5 x 2 bytes = the 20-byte Connect IQ write limit
MAX_PACKET_BYTES = 20

_HEADER = struct.Struct("<BBHIBB")  # version, flags, seq, watch_ms, hr, rr_count
_SEQ_MODULUS = 1 << 16
_WATCH_MS_MODULUS = 1 << 32
RESTART_BACKWARDS_MS = 5_000  # watch_ms going back more than this = watch rebooted
GAP_MS = 3_000  # watch_ms jumping more than this between packets = a gap in the beat stream


class RrFlags(IntFlag):
    NONE = 0
    HR_VALID = 1  # `hr` is a real reading
    SPLIT = 2  # the batch had more than 5 RR intervals and continues in the next packet


class RrCodecError(ValueError):
    """The bytes are not a valid version-1 RR packet."""


@dataclass(frozen=True)
class RrPacket:
    """One decoded packet, exactly as the watch sent it."""

    seq: int
    watch_ms: int
    hr_bpm: int | None  # None when the watch had no valid heart rate
    rr_ms: tuple[int, ...]
    flags: RrFlags = RrFlags.NONE
    version: int = PACKET_VERSION


def encode(packet: RrPacket) -> bytes:
    """Packet -> bytes (used by the simulator / fake watch and the tests)."""

    if len(packet.rr_ms) > MAX_RR_PER_PACKET:
        raise RrCodecError(f"at most {MAX_RR_PER_PACKET} RR intervals per packet")
    if not 0 <= packet.seq < _SEQ_MODULUS or not 0 <= packet.watch_ms < _WATCH_MS_MODULUS:
        raise RrCodecError("seq or watch_ms out of range")
    if any(not 0 <= rr < 1 << 16 for rr in packet.rr_ms):
        raise RrCodecError("RR interval out of uint16 range")
    flags = packet.flags | (RrFlags.HR_VALID if packet.hr_bpm is not None else RrFlags.NONE)
    hr = packet.hr_bpm if packet.hr_bpm is not None else 0
    if not 0 <= hr <= 255:
        raise RrCodecError("heart rate out of uint8 range")
    head = _HEADER.pack(packet.version, int(flags), packet.seq, packet.watch_ms, hr,
                        len(packet.rr_ms))
    return head + struct.pack(f"<{len(packet.rr_ms)}H", *packet.rr_ms)


def decode(payload: bytes) -> RrPacket:
    """Bytes -> packet. Raises RrCodecError on anything that breaks the contract."""

    if len(payload) < _HEADER.size:
        raise RrCodecError(f"{len(payload)} bytes is shorter than the 10-byte header")
    if len(payload) > MAX_PACKET_BYTES:
        raise RrCodecError(f"{len(payload)} bytes is longer than {MAX_PACKET_BYTES}")
    version, flag_bits, seq, watch_ms, hr, count = _HEADER.unpack_from(payload)
    if version != PACKET_VERSION:
        raise RrCodecError(f"unsupported version {version}")
    if count > MAX_RR_PER_PACKET:
        raise RrCodecError(f"rr_count {count} > {MAX_RR_PER_PACKET}")
    if len(payload) != _HEADER.size + 2 * count:
        raise RrCodecError(f"length {len(payload)} does not match rr_count {count}")
    flags = RrFlags(flag_bits & (RrFlags.HR_VALID | RrFlags.SPLIT))
    rr = struct.unpack_from(f"<{count}H", payload, _HEADER.size)
    return RrPacket(seq=seq, watch_ms=watch_ms,
                    hr_bpm=hr if flags & RrFlags.HR_VALID else None,
                    rr_ms=tuple(rr), flags=flags, version=version)


class Arrival(StrEnum):
    """What the tracker decided about one packet."""

    NEW = "new"  # first packet of a session, or the next one in order
    DUPLICATE = "duplicate"  # same seq as the last one: dropped
    LATE = "late"  # older than the last one: dropped
    NEW_SESSION = "new_session"  # the app restarted or the watch rebooted


@dataclass(frozen=True)
class RrFrame:
    """A packet plus the Pi-side facts about its arrival. This is what the HRV stage gets."""

    packet: RrPacket
    rx_monotonic: float  # time.monotonic() on the Pi at arrival: THE timestamp for alignment
    rx_wall: float  # time.time() at arrival, for logs only
    arrival: Arrival
    lost_before: int  # packets missing between the previous one and this one
    gap_before: bool  # watch_ms jumped > GAP_MS: do not join beats across this point
    session: int  # increases on every NEW_SESSION


@dataclass
class SequenceTracker:
    """Applies the duplicate / loss / restart rules of docs/packet_format.md."""

    session: int = 0
    received: int = 0
    duplicates: int = 0
    late: int = 0
    lost: int = 0
    _last_seq: int | None = field(default=None, repr=False)
    _last_watch_ms: int | None = field(default=None, repr=False)

    def accept(self, packet: RrPacket, rx_monotonic: float, rx_wall: float) -> RrFrame:
        """Classify one packet. Frames with DUPLICATE / LATE must be dropped by the caller."""

        lost, gap = 0, False
        if self._last_seq is None or self._last_watch_ms is None:
            arrival = Arrival.NEW
            self.session = self.session or 1  # the very first packet opens session 1
        else:
            back = (self._last_watch_ms - packet.watch_ms) % _WATCH_MS_MODULUS
            rebooted = 0 < back < _WATCH_MS_MODULUS // 2 and back > RESTART_BACKWARDS_MS
            restarted = packet.seq == 0 and self._last_seq != _SEQ_MODULUS - 1
            d = (packet.seq - self._last_seq) % _SEQ_MODULUS
            if rebooted or (restarted and d != 0):
                arrival = Arrival.NEW_SESSION
                self.session += 1
                gap = True
            elif d == 0:
                self.duplicates += 1
                return RrFrame(packet, rx_monotonic, rx_wall, Arrival.DUPLICATE, 0, False,
                               self.session)
            elif d >= _SEQ_MODULUS // 2:
                self.late += 1
                return RrFrame(packet, rx_monotonic, rx_wall, Arrival.LATE, 0, False,
                               self.session)
            else:
                arrival = Arrival.NEW
                lost = d - 1
                self.lost += lost
                step = (packet.watch_ms - self._last_watch_ms) % _WATCH_MS_MODULUS
                gap = lost > 0 or step > GAP_MS
        self.received += 1
        self._last_seq, self._last_watch_ms = packet.seq, packet.watch_ms
        return RrFrame(packet, rx_monotonic, rx_wall, arrival, lost, gap, self.session)

    def loss_fraction(self) -> float:
        """Lost / (received + lost) since start: one input to the quality flag."""

        total = self.received + self.lost
        return self.lost / total if total else 0.0
