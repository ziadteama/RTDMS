"""Generate synthetic PPG waveforms and faults for hardware-in-the-loop testing."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from .types import Channel, PpgPacket, SensorStatus


@dataclass(frozen=True, slots=True)
class WaveformConfig:
    """Configure the synthetic PPG waveform and fault generator."""

    seconds: float
    sample_rate_hz: float = 100.0
    batch_size: int | Sequence[int] = 20
    channels: Channel = Channel.INFRARED

    # Heart rate profile
    hr_profile: str = "constant"  # "constant", "ramp", "step"
    hr_constant: float = 60.0
    hr_ramp_start: float = 50.0
    hr_ramp_end: float = 120.0
    hr_step_before: float = 60.0
    hr_step_after: float = 90.0
    hr_step_time: float = 10.0

    # Signal shape and baseline
    pulse_amplitude: float = 18000.0
    dc_offset: float = 50000.0
    phase_offset: float = 0.0
    pulse_peak_phase: float = 0.18
    pulse_width_base: float = 0.06

    # Random seed
    seed: int | None = None

    # Noise & Wander
    baseline_drift: bool = False
    baseline_drift_amplitude: float = 500.0
    baseline_drift_frequency: float = 0.05
    white_noise_std: float = 0.0

    # Amplitude Modulation
    amplitude_modulation: bool = False
    amplitude_modulation_depth: float = 0.15
    amplitude_modulation_frequency: float = 0.2

    # Pulse-width variation
    pulse_width_variation: bool = False
    pulse_width_amplitude: float = 0.02
    pulse_width_frequency: float = 0.1

    # Artifacts & Motion
    motion_bursts: Sequence[tuple[int, int]] = field(default_factory=tuple)
    motion_noise_std: float = 50000.0
    motion_bias: float = 20000.0

    # Sensor status & hardware faults
    clipping: bool = False
    saturation: bool = False
    contact_loss: bool = False
    flatline: bool = False
    fifo_overflow: bool = False

    # Packet level faults
    sequence_start: int = 0
    packet_loss_indices: Sequence[int] = field(default_factory=tuple)
    packet_duplication_indices: Sequence[int] = field(default_factory=tuple)
    packet_reorder_indices: Sequence[int] = field(default_factory=tuple)
    sample_index_gap_indices: Sequence[int] = field(default_factory=tuple)
    sample_index_gap_size: int = 100

    # MCU Reset
    mcu_reset_packet_indices: Sequence[int] = field(default_factory=tuple)


def generate_ppg(config: WaveformConfig) -> Iterator[tuple[PpgPacket, list[int]]]:
    """Generate synthetic PPG packets according to the configuration."""

    rng = np.random.default_rng(config.seed)
    n_samples = int(np.round(config.seconds * config.sample_rate_hz))
    if n_samples <= 0:
        return

    t = np.arange(n_samples, dtype=np.float64) / config.sample_rate_hz

    # Compute phase based on selected profile
    if config.hr_profile == "constant":
        phi = (config.hr_constant / 60.0) * t + config.phase_offset
    elif config.hr_profile == "ramp":
        hr_start = config.hr_ramp_start
        hr_end = config.hr_ramp_end
        duration = config.seconds
        if duration > 0:
            phi = (
                (hr_start / 60.0) * t
                + ((hr_end - hr_start) / (120.0 * duration)) * (t**2)
                + config.phase_offset
            )
        else:
            phi = (hr_start / 60.0) * t + config.phase_offset
    elif config.hr_profile == "step":
        hr_before = config.hr_step_before
        hr_after = config.hr_step_after
        t_step = config.hr_step_time
        phi = (
            np.where(
                t < t_step,
                (hr_before / 60.0) * t,
                (hr_before / 60.0) * t_step + (hr_after / 60.0) * (t - t_step),
            )
            + config.phase_offset
        )
    else:
        phi = (config.hr_constant / 60.0) * t + config.phase_offset

    # Identify beat indices where phase crossed the peak phase threshold
    y = phi - config.pulse_peak_phase + 1e-9
    floored = np.floor(y)
    beat_indices_mask = np.zeros(n_samples, dtype=bool)
    if n_samples > 1:
        beat_indices_mask[1:] = floored[1:] > floored[:-1]
    beat_indices = np.where(beat_indices_mask)[0]
    global_beat_indices = [int(idx) for idx in beat_indices]

    # Compute Gaussian pulse shape
    theta = phi % 1.0
    d = (theta - config.pulse_peak_phase + 0.5) % 1.0 - 0.5

    if config.pulse_width_variation:
        w = config.pulse_width_base + config.pulse_width_amplitude * np.sin(
            2.0 * np.pi * config.pulse_width_frequency * t
        )
    else:
        w = np.full(n_samples, config.pulse_width_base, dtype=np.float64)

    pulse = np.exp(-((d / w) ** 2))

    # Construct signal. Annotated shape-agnostically: numpy infers a strictly 1-D
    # type from np.full, but the arithmetic below yields general-shape arrays.
    signal: NDArray[np.float64] = np.full(n_samples, config.dc_offset, dtype=np.float64)
    if not config.flatline and not config.contact_loss:
        if config.amplitude_modulation:
            amp = config.pulse_amplitude * (
                1.0
                + config.amplitude_modulation_depth
                * np.sin(2.0 * np.pi * config.amplitude_modulation_frequency * t)
            )
            signal = signal + amp * pulse
        else:
            signal = signal + config.pulse_amplitude * pulse

    # Baseline drift
    if config.baseline_drift:
        drift = config.baseline_drift_amplitude * np.sin(
            2.0 * np.pi * config.baseline_drift_frequency * t
        )
        drift += 0.5 * config.baseline_drift_amplitude * np.sin(
            2.0 * np.pi * (config.baseline_drift_frequency * 0.4) * t
        )
        signal = signal + drift

    # White noise
    if config.white_noise_std > 0.0:
        signal = signal + rng.normal(0.0, config.white_noise_std, size=n_samples)

    # Motion bursts
    motion_mask = np.zeros(n_samples, dtype=bool)
    for start, end in config.motion_bursts:
        s = max(0, start)
        e = min(n_samples, end)
        if s < e:
            motion_mask[s:e] = True

    if np.any(motion_mask):
        num_motion_samples = np.sum(motion_mask)
        signal[motion_mask] += rng.normal(0.0, config.motion_noise_std, size=num_motion_samples)
        signal[motion_mask] += config.motion_bias

    # Contact loss sets signal to flat 0
    if config.contact_loss:
        signal[:] = 0.0

    # Clipping
    if config.clipping:
        signal = signal + 250000.0

    # Clip to unsigned 18-bit range [0, 262143] and round
    signal = np.clip(signal, 0.0, 262143.0)
    adc_samples = np.round(signal).astype(np.int64)

    # Construct channel interleaved sample rows
    samples_list: list[tuple[int, ...]] = []
    for n in range(n_samples):
        row = []
        if config.channels & Channel.RED:
            row.append(int(adc_samples[n]))
        if config.channels & Channel.INFRARED:
            row.append(int(adc_samples[n]))
        samples_list.append(tuple(row))

    # Chunk into packets
    packets: list[tuple[PpgPacket, list[int]]] = []
    sample_index = 0
    packet_index = 0
    sequence_counter = config.sequence_start
    first_sample_index_counter = 0

    if isinstance(config.batch_size, int):
        batch_sizes: Sequence[int] = [config.batch_size]
    else:
        batch_sizes = config.batch_size

    while sample_index < n_samples:
        b_size = batch_sizes[packet_index % len(batch_sizes)]
        current_batch_size = min(b_size, n_samples - sample_index)
        if current_batch_size <= 0:
            break

        packet_samples = tuple(samples_list[sample_index : sample_index + current_batch_size])
        packet_beats = [
            idx
            for idx in global_beat_indices
            if sample_index <= idx < sample_index + current_batch_size
        ]

        if packet_index in config.mcu_reset_packet_indices:
            sequence_counter = 0
            first_sample_index_counter = 0
            status_bits = SensorStatus.SENSOR_RESET
        else:
            status_bits = SensorStatus.NONE

        if config.saturation:
            status_bits |= SensorStatus.SATURATED
        if config.contact_loss:
            status_bits |= SensorStatus.CONTACT_LOST
        if config.fifo_overflow:
            status_bits |= SensorStatus.FIFO_OVERFLOW

        first_sample_index_field = first_sample_index_counter
        if packet_index in config.sample_index_gap_indices:
            first_sample_index_field += config.sample_index_gap_size

        seq_field = sequence_counter % 65536
        idx_field = first_sample_index_field % 4294967296

        packet = PpgPacket(
            version=1,
            sequence=seq_field,
            first_sample_index=idx_field,
            channels=config.channels,
            status=status_bits,
            samples=packet_samples,
        )
        packets.append((packet, packet_beats))

        first_sample_index_counter = first_sample_index_field + current_batch_size
        sequence_counter += 1
        sample_index += current_batch_size
        packet_index += 1

    # Post-process list to apply packet-level faults (loss, duplication, reordering)
    final_packets: list[tuple[PpgPacket, list[int]]] = []
    i = 0
    num_packets = len(packets)
    while i < num_packets:
        if i in config.packet_reorder_indices and i + 1 < num_packets:
            p1_idx = i + 1
            p2_idx = i
            pair = [p1_idx, p2_idx]
            for idx in pair:
                if idx in config.packet_loss_indices:
                    continue
                copies = 2 if idx in config.packet_duplication_indices else 1
                for _ in range(copies):
                    final_packets.append(packets[idx])
            i += 2
        else:
            if i in config.packet_loss_indices:
                i += 1
                continue
            copies = 2 if i in config.packet_duplication_indices else 1
            for _ in range(copies):
                final_packets.append(packets[i])
            i += 1

    yield from final_packets
