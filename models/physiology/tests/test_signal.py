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
