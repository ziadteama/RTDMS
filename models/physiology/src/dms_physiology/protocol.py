"""Versioned binary codec and continuity tracking for wearable PPG packets."""

from __future__ import annotations

import struct
from collections import deque

from .types import Channel, PacketObservation, PpgPacket, SensorStatus

PACKET_VERSION = 1
MAX_ADC_VALUE = (1 << 18) - 1
MAX_PACKET_SAMPLES = 255
_HEADER = struct.Struct("!BBHIBB")
_SEQUENCE_MODULUS = 1 << 16
_SAMPLE_INDEX_MODULUS = 1 << 32


class PacketCodecError(ValueError):
    """Raised when a packet violates the transport wire contract."""


class PacketCodec:
    """Encode and decode the compact BLE application payload."""

    @staticmethod
    def encode(packet: PpgPacket) -> bytes:
        """Encode a validated packet into its BLE notification payload."""

        PacketCodec._validate_packet(packet)
        payload = bytearray(
            _HEADER.pack(
                packet.version,
                int(packet.status),
                packet.sequence,
                packet.first_sample_index,
                packet.sample_count,
                int(packet.channels),
            )
        )
        for row in packet.samples:
            for value in row:
                payload.extend(value.to_bytes(3, byteorder="big"))
        return bytes(payload)

    @staticmethod
    def decode(payload: bytes) -> PpgPacket:
        """Decode one complete BLE notification payload."""

        if len(payload) < _HEADER.size:
            raise PacketCodecError("packet is shorter than the fixed header")

        version, status, sequence, sample_index, count, channel_bits = _HEADER.unpack_from(payload)
        channels = Channel(channel_bits)
        enabled_channels = PacketCodec._channel_count(channels)
        expected_size = _HEADER.size + count * enabled_channels * 3
        if len(payload) != expected_size:
            raise PacketCodecError(
                f"packet length {len(payload)} does not match expected length {expected_size}"
            )

        values: list[tuple[int, ...]] = []
        offset = _HEADER.size
        for _ in range(count):
            row = tuple(
                int.from_bytes(payload[offset + index * 3 : offset + (index + 1) * 3], "big")
                for index in range(enabled_channels)
            )
            values.append(row)
            offset += enabled_channels * 3

        packet = PpgPacket(
            version=version,
            sequence=sequence,
            first_sample_index=sample_index,
            channels=channels,
            status=SensorStatus(status),
            samples=tuple(values),
        )
        PacketCodec._validate_packet(packet)
        return packet

    @staticmethod
    def _validate_packet(packet: PpgPacket) -> None:
        if packet.version != PACKET_VERSION:
            raise PacketCodecError(f"unsupported packet version {packet.version}")
        if not 0 <= packet.sequence < _SEQUENCE_MODULUS:
            raise PacketCodecError("sequence must be an unsigned 16-bit integer")
        if not 0 <= packet.first_sample_index < _SAMPLE_INDEX_MODULUS:
            raise PacketCodecError("sample index must be an unsigned 32-bit integer")
        if not 1 <= packet.sample_count <= MAX_PACKET_SAMPLES:
            raise PacketCodecError("packet must contain between one and 255 samples")
        channel_count = PacketCodec._channel_count(packet.channels)
        if int(packet.status) & ~int(
            SensorStatus.FIFO_OVERFLOW
            | SensorStatus.SENSOR_RESET
            | SensorStatus.SATURATED
            | SensorStatus.CONTACT_LOST
        ):
            raise PacketCodecError("packet contains unknown sensor status bits")
        for row in packet.samples:
            if len(row) != channel_count:
                raise PacketCodecError("sample row does not match enabled channel count")
            for value in row:
                if not 0 <= value <= MAX_ADC_VALUE:
                    raise PacketCodecError("optical sample must be an unsigned 18-bit value")

    @staticmethod
    def _channel_count(channels: Channel) -> int:
        if channels not in (Channel.RED, Channel.INFRARED, Channel.RED | Channel.INFRARED):
            raise PacketCodecError("packet must enable one or two known optical channels")
        return int(channels).bit_count()


class PacketTracker:
    """Track sequence and sample-index continuity across one wearable session."""

    def __init__(self) -> None:
        self._previous: PpgPacket | None = None
        self._seen: deque[tuple[int, int]] = deque(maxlen=16)
        self._session_id: int = 0

    def reset(self) -> None:
        """Forget continuity state, for example after an explicit new session."""

        self._previous = None
        self._seen.clear()
        self._session_id += 1

    def observe(self, packet: PpgPacket) -> PacketObservation:
        """Record an incoming packet and return its continuity assessment."""

        PacketCodec._validate_packet(packet)

        reset_detected = bool(packet.status & SensorStatus.SENSOR_RESET)
        if reset_detected:
            self._session_id += 1
            self._previous = packet
            self._seen.clear()
            self._seen.append((packet.sequence, packet.first_sample_index))
            return PacketObservation(
                sequence_gap=0,
                sample_gap=0,
                duplicate=False,
                reordered=False,
                reset_detected=True,
                session_id=self._session_id,
            )

        duplicate = (packet.sequence, packet.first_sample_index) in self._seen

        previous = self._previous
        if previous is None:
            self._previous = packet
            self._seen.append((packet.sequence, packet.first_sample_index))
            return PacketObservation(
                sequence_gap=0,
                sample_gap=0,
                duplicate=duplicate,
                reordered=False,
                reset_detected=False,
                session_id=self._session_id,
            )

        sequence_step = (packet.sequence - previous.sequence) % _SEQUENCE_MODULUS
        expected_index = (
            previous.first_sample_index + previous.sample_count
        ) % _SAMPLE_INDEX_MODULUS
        sample_step = (packet.first_sample_index - expected_index) % _SAMPLE_INDEX_MODULUS
        if sample_step >= 2**31:
            sample_step -= _SAMPLE_INDEX_MODULUS

        reordered = not duplicate and sequence_step > _SEQUENCE_MODULUS // 2
        if not duplicate and not reordered:
            self._previous = packet
            self._seen.append((packet.sequence, packet.first_sample_index))

        return PacketObservation(
            sequence_gap=0 if duplicate or reordered else max(sequence_step - 1, 0),
            sample_gap=0 if duplicate or reordered else max(sample_step, 0),
            duplicate=duplicate,
            reordered=reordered,
            reset_detected=False,
            session_id=self._session_id,
        )
