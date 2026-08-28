"""Immutable value objects shared by transport components."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag, StrEnum


class Channel(IntFlag):
    """Optical channels present in a packet, in wire-order bit order."""

    NONE = 0
    RED = 1
    INFRARED = 2


class SensorStatus(IntFlag):
    """Status reported by the wearable alongside sampled PPG data."""

    NONE = 0
    FIFO_OVERFLOW = 1
    SENSOR_RESET = 2
    SATURATED = 4
    CONTACT_LOST = 8


class QualityState(StrEnum):
    """Whether a feature window is safe to use for fatigue inference."""

    GOOD = "good"
    DEGRADED = "degraded"
    BAD = "bad"


class QualityReason(IntFlag):
    """Independent causes that lower confidence in a PPG window."""

    NONE = 0
    PACKET_LOSS = 1
    SENSOR_FAULT = 2
    CLIPPING = 4
    ARTIFACTS = 8
    INSUFFICIENT_BEATS = 16
    FLATLINE = 32


@dataclass(frozen=True, slots=True)
class QualityReport:
    """Quality measurements and the resulting quality gate."""

    state: QualityState
    score: float
    reasons: QualityReason
    packet_loss_fraction: float
    artifact_fraction: float
    clipping_fraction: float
    valid_interval_count: int


@dataclass(frozen=True, slots=True)
class PpgPacket:
    """A decoded wearable packet containing interleaved optical samples.

    ``samples`` is ordered by sample then by the enabled channels in ascending
    bit order. Each value is an unsigned 18-bit ADC reading.
    """

    version: int
    sequence: int
    first_sample_index: int
    channels: Channel
    status: SensorStatus
    samples: tuple[tuple[int, ...], ...]

    @property
    def sample_count(self) -> int:
        """Return the number of time samples in this packet."""

        return len(self.samples)


@dataclass(frozen=True, slots=True)
class PpgFrame:
    """A packet annotated with its Pi-side receive timestamp and sample rate."""

    packet: PpgPacket
    sample_rate_hz: int
    received_at_seconds: float


@dataclass(frozen=True, slots=True)
class PacketObservation:
    """Result of comparing an incoming packet with the previous packet."""

    sequence_gap: int
    sample_gap: int
    duplicate: bool
    reordered: bool
    reset_detected: bool
