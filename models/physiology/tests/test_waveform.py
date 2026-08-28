"""Tests for the synthetic PPG waveform and fault generator."""

from __future__ import annotations

import numpy as np

from dms_physiology.protocol import PacketCodec
from dms_physiology.types import Channel, PpgPacket, SensorStatus
from dms_physiology.waveform import WaveformConfig, generate_ppg


def test_seeded_determinism() -> None:
    """Verify that same seed produces identical packet streams and ground truth."""
    config1 = WaveformConfig(
        seconds=10.0,
        sample_rate_hz=100.0,
        seed=12345,
        baseline_drift=True,
        white_noise_std=100.0,
    )
    config2 = WaveformConfig(
        seconds=10.0,
        sample_rate_hz=100.0,
        seed=12345,
        baseline_drift=True,
        white_noise_std=100.0,
    )

    stream1 = list(generate_ppg(config1))
    stream2 = list(generate_ppg(config2))

    assert len(stream1) == len(stream2)
    for (p1, b1), (p2, b2) in zip(stream1, stream2, strict=True):
        assert p1 == p2
        assert b1 == b2


def test_types_and_synchronous() -> None:
    """Verify that the generator yields PpgPacket objects and beat list synchronously."""
    config = WaveformConfig(seconds=2.0)
    generator = generate_ppg(config)
    
    # Assert generator behaves synchronously
    packet, beats = next(generator)
    assert isinstance(packet, PpgPacket)
    assert isinstance(beats, list)
    assert all(isinstance(b, int) for b in beats)


def test_ground_truth_beat_indices() -> None:
    """Verify that the beat indices correspond to local peaks in the PPG pulses."""
    config = WaveformConfig(
        seconds=10.0,
        sample_rate_hz=100.0,
        hr_constant=60.0,
        seed=42,
    )

    packets_with_beats = list(generate_ppg(config))
    
    # Reconstruct the continuous signal
    all_samples: list[int] = []
    for packet, _ in packets_with_beats:
        for row in packet.samples:
            all_samples.append(row[0])
            
    all_beats: list[int] = []
    for _, beats in packets_with_beats:
        all_beats.extend(beats)

    # A beat index should be a local maximum or close to it
    for idx in all_beats:
        if 0 < idx < len(all_samples) - 1:
            val_prev = all_samples[idx - 1]
            val_curr = all_samples[idx]
            val_next = all_samples[idx + 1]
            # Since the peak phase is 0.18, let's verify it is local maximum
            assert val_curr >= val_prev
            assert val_curr >= val_next


def test_hr_profile_constant() -> None:
    """Verify constant HR has constant intervals between beats."""
    config = WaveformConfig(
        seconds=10.0,
        sample_rate_hz=100.0,
        hr_constant=60.0,
    )
    beats = []
    for _, pb in generate_ppg(config):
        beats.extend(pb)
        
    intervals = np.diff(beats)
    # At 60 bpm and 100 Hz, intervals should be exactly 100 samples
    assert np.all(intervals == 100)


def test_hr_profile_ramp() -> None:
    """Verify linear HR ramp changes intervals monotonically."""
    config = WaveformConfig(
        seconds=20.0,
        sample_rate_hz=100.0,
        hr_profile="ramp",
        hr_ramp_start=60.0,  # 1.0s interval
        hr_ramp_end=120.0,   # 0.5s interval
    )
    beats = []
    for _, pb in generate_ppg(config):
        beats.extend(pb)
        
    intervals = np.diff(beats)
    # The intervals should decrease as heart rate ramps up
    for i in range(len(intervals) - 1):
        assert intervals[i] >= intervals[i + 1]


def test_hr_profile_step() -> None:
    """Verify step change in HR changes intervals abruptly."""
    config = WaveformConfig(
        seconds=20.0,
        sample_rate_hz=100.0,
        hr_profile="step",
        hr_step_before=60.0,  # 100 samples
        hr_step_after=120.0,  # 50 samples
        hr_step_time=10.0,
    )
    beats = []
    for _, pb in generate_ppg(config):
        beats.extend(pb)
        
    # Find beats before 10.0s (index 1000) and after
    beats_before = [b for b in beats if b < 1000]
    beats_after = [b for b in beats if b >= 1000]
    
    intervals_before = np.diff(beats_before)
    intervals_after = np.diff(beats_after)
    
    assert np.all(intervals_before == 100)
    assert np.all(intervals_after == 50)


def test_baseline_drift() -> None:
    """Verify baseline drift wanders slowly."""
    config_no_drift = WaveformConfig(seconds=10.0, baseline_drift=False)
    config_drift = WaveformConfig(
        seconds=10.0, baseline_drift=True, baseline_drift_amplitude=2000.0
    )

    p_no = list(generate_ppg(config_no_drift))
    p_dr = list(generate_ppg(config_drift))

    samples_no = [row[0] for p, _ in p_no for row in p.samples]
    samples_dr = [row[0] for p, _ in p_dr for row in p.samples]

    # No drift should stay strictly within baseline offset + pulse
    # Drift should cause much larger variations
    assert np.std(samples_dr) > np.std(samples_no)


def test_white_noise() -> None:
    """Verify white noise increases high frequency variation."""
    config_no_noise = WaveformConfig(seconds=5.0, white_noise_std=0.0)
    config_noise = WaveformConfig(seconds=5.0, white_noise_std=1000.0, seed=42)

    p_no = list(generate_ppg(config_no_noise))
    p_ns = list(generate_ppg(config_noise))

    samples_no = np.array([row[0] for p, _ in p_no for row in p.samples])
    samples_ns = np.array([row[0] for p, _ in p_ns for row in p.samples])

    diff_no = np.diff(samples_no)
    diff_ns = np.diff(samples_ns)

    # High frequency differences (successive samples) should be much higher with noise
    assert np.std(diff_ns) > np.std(diff_no)


def test_amplitude_modulation() -> None:
    """Verify amplitude modulation varies the peak amplitudes of pulses."""
    config = WaveformConfig(
        seconds=20.0,
        sample_rate_hz=100.0,
        amplitude_modulation=True,
        amplitude_modulation_depth=0.2,
        amplitude_modulation_frequency=0.2,
    )
    packets = list(generate_ppg(config))
    samples = [row[0] for p, _ in packets for row in p.samples]
    beats = [b for _, pb in packets for b in pb]
    
    peak_values = [samples[b] for b in beats if b < len(samples)]
    # Peak values should not be constant due to amplitude modulation
    assert np.std(peak_values) > 100.0
    assert min(peak_values) < max(peak_values)


def test_pulse_width_variation() -> None:
    """Verify pulse width variation changes pulse width over time."""
    config = WaveformConfig(
        seconds=20.0,
        sample_rate_hz=100.0,
        pulse_width_variation=True,
        pulse_width_amplitude=0.02,
        pulse_width_frequency=0.1,
    )
    packets = list(generate_ppg(config))
    samples = [row[0] for p, _ in packets for row in p.samples]
    beats = [b for _, pb in packets for b in pb]

    # Measure the width of two different pulses at their half-maxima
    # Beat 1 (near time 1s) and Beat 10 (near time 10s)
    widths = []
    for b_idx in [beats[1], beats[8]]:
        # Find points around the peak that are 50% height
        peak_val = samples[b_idx]
        base_val = 50000.0
        half_height = base_val + 0.5 * (peak_val - base_val)
        
        # Search backwards
        left = b_idx
        while left > 0 and samples[left] > half_height:
            left -= 1
        # Search forwards
        right = b_idx
        while right < len(samples) - 1 and samples[right] > half_height:
            right += 1
            
        widths.append(right - left)

    assert widths[0] != widths[1]


def test_motion_bursts() -> None:
    """Verify motion bursts perturb signal in specified range and return range."""
    bursts = ((50, 100), (250, 300))
    config = WaveformConfig(
        seconds=5.0,
        sample_rate_hz=100.0,
        motion_bursts=bursts,
        motion_noise_std=100000.0,
        seed=42,
    )
    packets = list(generate_ppg(config))
    samples = [row[0] for p, _ in packets for row in p.samples]

    # Verify signal variance inside the burst is much higher than outside
    inside_burst = samples[50:100] + samples[250:300]
    outside_burst = samples[0:50] + samples[100:250] + samples[300:500]

    assert np.std(inside_burst) > 5 * np.std(outside_burst)
    assert config.motion_bursts == bursts


def test_clipping() -> None:
    """Verify clipping pins values at the maximum ADC range."""
    config = WaveformConfig(seconds=5.0, clipping=True)
    packets = list(generate_ppg(config))
    samples = [row[0] for p, _ in packets for row in p.samples]

    # High percentage of samples should be pinned at MAX_ADC_VALUE (262143)
    max_val = 262143
    clip_count = sum(1 for s in samples if s == max_val)
    assert clip_count > 0.5 * len(samples)


def test_saturation() -> None:
    """Verify saturation status flag is propagated."""
    config = WaveformConfig(seconds=2.0, saturation=True)
    packets = list(generate_ppg(config))
    assert all(bool(p.status & SensorStatus.SATURATED) for p, _ in packets)


def test_contact_loss() -> None:
    """Verify contact loss sets flag and flatlines signal to 0."""
    config = WaveformConfig(seconds=2.0, contact_loss=True)
    packets = list(generate_ppg(config))
    for p, _ in packets:
        assert bool(p.status & SensorStatus.CONTACT_LOST)
        for row in p.samples:
            assert all(v == 0 for v in row)


def test_flatline() -> None:
    """Verify flatline has zero variance and baseline DC offset."""
    config = WaveformConfig(seconds=2.0, flatline=True)
    packets = list(generate_ppg(config))
    samples = [row[0] for p, _ in packets for row in p.samples]
    assert np.std(samples) == 0.0
    assert all(s == 50000 for s in samples)


def test_packet_loss() -> None:
    """Verify packet loss drops packets, creating gaps in sequence and samples."""
    # Loss at packet index 2 (third packet)
    config = WaveformConfig(
        seconds=5.0,
        batch_size=20,
        packet_loss_indices=(2,),
    )
    packets = [p for p, _ in generate_ppg(config)]
    
    # We should have sequence numbers like: 0, 1, 3, 4... (packet 2 dropped)
    assert packets[0].sequence == 0
    assert packets[1].sequence == 1
    assert packets[2].sequence == 3
    
    # Sample index should also have a gap: first_sample_index at 2 should be 60 (normally 40)
    assert packets[1].first_sample_index == 20
    assert packets[2].first_sample_index == 60


def test_packet_duplication() -> None:
    """Verify packet duplication repeats a packet with identical headers/data."""
    config = WaveformConfig(
        seconds=5.0,
        batch_size=20,
        packet_duplication_indices=(1,),
    )
    packets = [p for p, _ in generate_ppg(config)]

    # Packet at index 1 is duplicated, so index 1 and 2 in returned packets are identical
    assert packets[1] == packets[2]
    # Subsequent packet has sequence 2 and sample index 40
    assert packets[3].sequence == 2
    assert packets[3].first_sample_index == 40


def test_packet_reordering() -> None:
    """Verify packet reordering swaps the order of packets in the stream."""
    config = WaveformConfig(
        seconds=5.0,
        batch_size=20,
        packet_reorder_indices=(1,),
    )
    packets = [p for p, _ in generate_ppg(config)]

    # Normally sequence is 0, 1, 2, 3...
    # Reordering swaps index 1 and 2
    assert packets[0].sequence == 0
    assert packets[1].sequence == 2
    assert packets[2].sequence == 1
    assert packets[3].sequence == 3

    assert packets[1].first_sample_index == 40
    assert packets[2].first_sample_index == 20


def test_sequence_wraparound() -> None:
    """Verify sequence number wraps around 65535 cleanly."""
    config = WaveformConfig(
        seconds=5.0,
        batch_size=10,
        sequence_start=65534,
    )
    packets = [p for p, _ in generate_ppg(config)]
    
    assert packets[0].sequence == 65534
    assert packets[1].sequence == 65535
    assert packets[2].sequence == 0
    assert packets[3].sequence == 1


def test_sample_index_gaps() -> None:
    """Verify sample-index gaps are created without dropping sequence numbers."""
    config = WaveformConfig(
        seconds=5.0,
        batch_size=20,
        sample_index_gap_indices=(2,),
        sample_index_gap_size=100,
    )
    packets = [p for p, _ in generate_ppg(config)]

    # Gaps shouldn't drop sequence number
    assert packets[0].sequence == 0
    assert packets[1].sequence == 1
    assert packets[2].sequence == 2

    # But sample index has a gap
    assert packets[1].first_sample_index == 20
    assert packets[2].first_sample_index == 140  # 40 + 100 gap
    assert packets[3].first_sample_index == 160  # 140 + 20


def test_fifo_overflow() -> None:
    """Verify FIFO overflow flag is set correctly."""
    config = WaveformConfig(seconds=2.0, fifo_overflow=True)
    packets = [p for p, _ in generate_ppg(config)]
    assert all(bool(p.status & SensorStatus.FIFO_OVERFLOW) for p in packets)


def test_mcu_reset() -> None:
    """Verify MCU reset sets flag and restarts sequence and sample index at 0."""
    config = WaveformConfig(
        seconds=5.0,
        batch_size=20,
        mcu_reset_packet_indices=(2,),
    )
    packets = [p for p, _ in generate_ppg(config)]

    # Packet 2 resets
    assert packets[0].sequence == 0
    assert packets[0].first_sample_index == 0

    assert packets[1].sequence == 1
    assert packets[1].first_sample_index == 20

    # MCU Reset at packet 2
    assert bool(packets[2].status & SensorStatus.SENSOR_RESET)
    assert packets[2].sequence == 0
    assert packets[2].first_sample_index == 0

    # Increments from 0 again
    assert packets[3].sequence == 1
    assert packets[3].first_sample_index == 20


def test_variable_batch_size() -> None:
    """Verify configurable packet batch sizes (3 to 79) and list cycling."""
    # Test batch size 3
    c3 = WaveformConfig(seconds=1.0, batch_size=3)
    p3 = [p for p, _ in generate_ppg(c3)]
    assert all(p.sample_count == 3 for p in p3[:-1])

    # Test batch size 79
    c79 = WaveformConfig(seconds=3.0, batch_size=79)
    p79 = [p for p, _ in generate_ppg(c79)]
    assert all(p.sample_count == 79 for p in p79[:-1])

    # Test variable cycling
    cvar = WaveformConfig(seconds=2.0, batch_size=(10, 15, 20))
    pvar = [p for p, _ in generate_ppg(cvar)]
    assert pvar[0].sample_count == 10
    assert pvar[1].sample_count == 15
    assert pvar[2].sample_count == 20
    assert pvar[3].sample_count == 10


def test_peaks_straddling_packet_boundary() -> None:
    """Verify a peak can span two packets."""
    # Place a peak exactly at the sample boundary of 20 (sample index 20 is the start of packet 1)
    # The Gaussian pulse has a width of 0.06 seconds (6 samples).
    # So the pulse at index 20 will span both packets (samples 14 to 26).
    config = WaveformConfig(
        seconds=2.0,
        sample_rate_hz=100.0,
        batch_size=20,
        hr_constant=60.0,
        phase_offset=-0.02,
        # Align peak to sample 20: 20/100 = 0.20 phase.
        # With offset -0.02: 20/100 - 0.02 = 0.18 (the peak phase).
    )

    packets = [p for p, _ in generate_ppg(config)]
    
    # Packet 0: samples 0 to 19 (peak is at 20)
    # Packet 1: samples 20 to 39
    p0 = packets[0]
    p1 = packets[1]

    # Verify that the samples towards the end of p0 are rising, and beginning of p1 are falling
    # Samples in p0: p0.samples[-1][0] is at index 19 (near peak).
    # Samples in p1: p1.samples[0][0] is at index 20 (peak itself),
    # and p1.samples[1][0] is index 21.
    assert p0.samples[-1][0] > p0.samples[-5][0] # rising systolic
    assert p1.samples[0][0] > p0.samples[-1][0]  # peak is at index 20
    assert p1.samples[0][0] > p1.samples[1][0]  # falling diastolic


def test_property_codec_roundtrip() -> None:
    """Property test verifying PacketCodec round-trip on all generated configurations."""
    # Test a bunch of configurations with various faults enabled
    configs = [
        WaveformConfig(seconds=5.0, baseline_drift=True, white_noise_std=10.0),
        WaveformConfig(seconds=5.0, clipping=True),
        WaveformConfig(seconds=5.0, saturation=True),
        WaveformConfig(seconds=5.0, contact_loss=True),
        WaveformConfig(seconds=5.0, flatline=True),
        WaveformConfig(seconds=5.0, fifo_overflow=True),
        WaveformConfig(seconds=5.0, channels=Channel.RED),
        WaveformConfig(seconds=5.0, channels=Channel.RED | Channel.INFRARED),
        WaveformConfig(seconds=5.0, mcu_reset_packet_indices=(1, 3)),
        WaveformConfig(seconds=5.0, batch_size=(5, 10, 15)),
    ]

    for cfg in configs:
        for packet, _ in generate_ppg(cfg):
            encoded = PacketCodec.encode(packet)
            decoded = PacketCodec.decode(encoded)
            assert decoded == packet
