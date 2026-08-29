from __future__ import annotations

import numpy as np

from dms_physiology.features import extract_features
from dms_physiology.signal import FloatRingBuffer, Interval, IntervalRejector, StreamingBandpass


def test_ring_buffer_keeps_latest_values_after_wrap() -> None:
    ring = FloatRingBuffer(4)
    ring.append(np.asarray([1, 2, 3], dtype=np.float32))
    ring.append(np.asarray([4, 5], dtype=np.float32))
    assert ring.latest().tolist() == [2.0, 3.0, 4.0, 5.0]


def test_streaming_filter_is_chunk_boundary_stable() -> None:
    samples = np.sin(np.linspace(0, 20, 1_000)).astype(np.float32)
    one_batch = StreamingBandpass(100).process(samples)
    chunked_filter = StreamingBandpass(100)
    chunked = np.concatenate(
        [chunked_filter.process(samples[:333]), chunked_filter.process(samples[333:])]
    )
    assert np.allclose(one_batch, chunked, atol=1e-5)


def test_interval_rejector_rejects_large_local_jump() -> None:
    rejector = IntervalRejector(100)
    intervals = rejector.process((0, 100, 200, 300, 400, 700))
    assert [item.valid for item in intervals] == [True, True, True, True, False]


def test_features_use_only_valid_intervals() -> None:
    snapshot = extract_features(
        (
            Interval(100, 1_000.0, True),
            Interval(200, 1_010.0, True),
            Interval(300, 990.0, True),
            Interval(400, 300.0, False),
        )
    )
    assert snapshot is not None
    assert snapshot.valid_interval_count == 3
    assert 59.0 < snapshot.mean_hr_bpm < 61.0


def test_scipy_equivalence() -> None:
    from scipy.signal import butter, find_peaks, sosfilt

    from dms_physiology.signal import _find_peaks, _sosfilt
    from dms_physiology.waveform import WaveformConfig, generate_ppg

    # 1. Filter equivalence
    sos = butter(2, [0.5, 5.0], btype="bandpass", fs=100.0, output="sos")
    x = np.random.randn(5000).astype(np.float32)
    zi_scipy = np.zeros((sos.shape[0], 2), dtype=np.float64)
    zi_my = np.zeros((sos.shape[0], 2), dtype=np.float64)

    y_scipy1, zi_scipy = sosfilt(sos, x[:2500], zi=zi_scipy)
    y_scipy2, zi_scipy = sosfilt(sos, x[2500:], zi=zi_scipy)
    y_scipy = np.concatenate([y_scipy1, y_scipy2])

    y_my1, zi_my = _sosfilt(sos, x[:2500], zi=zi_my)
    y_my2, zi_my = _sosfilt(sos, x[2500:], zi=zi_my)
    y_my = np.concatenate([y_my1, y_my2])

    assert np.max(np.abs(y_scipy - y_my)) < 1e-6

    # 2. Peak detector equivalence on 5 varied signals
    configs = [
        WaveformConfig(seconds=30.0, hr_constant=60, white_noise_std=0.0), # clean
        WaveformConfig(seconds=30.0, hr_constant=70, white_noise_std=500.0), # noisy
        # drifting
        WaveformConfig(
            seconds=30.0, hr_constant=80, baseline_drift=True,
            baseline_drift_amplitude=1000.0,
        ),
        # amplitude modulated
        WaveformConfig(
            seconds=30.0, hr_constant=65, amplitude_modulation=True,
            amplitude_modulation_depth=0.5,
        ),
        # motion burst
        WaveformConfig(
            seconds=30.0, hr_constant=90, motion_bursts=[(1000, 1500)],
            motion_noise_std=10000.0,
        ),
    ]

    for idx, config in enumerate(configs):
        # generate raw signal
        packets = list(generate_ppg(config))
        # collect all samples
        all_samples = []
        for p, _ in packets:
            for s in p.samples:
                all_samples.append(s[0]) # take red channel or whatever is first

        # filter it using our filter
        signal = np.array(all_samples, dtype=np.float32)
        filtered = StreamingBandpass(100.0).process(signal)

        # prepare energy as the detector does
        history = np.maximum(filtered, 0.0)
        energy = np.square(history)
        threshold = float(np.median(energy) + 0.35 * np.std(energy))
        epsilon = float(np.finfo(np.float32).eps)

        h = max(threshold, epsilon)
        d = max(30, 1)
        p = max(float(np.std(energy)) * 0.2, epsilon)

        scipy_peaks, _ = find_peaks(energy, height=h, distance=d, prominence=p)
        my_peaks = _find_peaks(energy, height=h, distance=d, prominence=p)

        assert np.array_equal(scipy_peaks, my_peaks), (
            f"Peaks mismatch on signal {idx}: "
            f"scipy={len(scipy_peaks)} ours={len(my_peaks)}"
        )

