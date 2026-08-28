"""Bounded streaming PPG filtering, peak detection, and IBI rejection."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.signal import butter, find_peaks, sosfilt

FloatArray = NDArray[np.float32]


class FloatRingBuffer:
    """Fixed-size float32 ring buffer with constant memory use."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._data = np.zeros(capacity, dtype=np.float32)
        self._capacity = capacity
        self._size = 0
        self._write_index = 0

    @property
    def size(self) -> int:
        return self._size

    def append(self, values: FloatArray) -> None:
        array = np.asarray(values, dtype=np.float32).reshape(-1)
        if array.size >= self._capacity:
            self._data[:] = array[-self._capacity :]
            self._size = self._capacity
            self._write_index = 0
            return
        first = min(array.size, self._capacity - self._write_index)
        self._data[self._write_index : self._write_index + first] = array[:first]
        remainder = array.size - first
        if remainder:
            self._data[:remainder] = array[first:]
        self._write_index = (self._write_index + array.size) % self._capacity
        self._size = min(self._capacity, self._size + array.size)

    def latest(self, count: int | None = None) -> FloatArray:
        requested = self._size if count is None else min(max(count, 0), self._size)
        start = (self._write_index - requested) % self._capacity
        if requested == 0:
            return np.empty(0, dtype=np.float32)
        if start + requested <= self._capacity:
            return self._data[start : start + requested].copy()
        return np.concatenate(
            (self._data[start:], self._data[: (start + requested) % self._capacity])
        )


class StreamingBandpass:
    """Causal Butterworth SOS filter retaining state across packet boundaries."""

    def __init__(
        self, sample_rate_hz: float, lowcut_hz: float = 0.5, highcut_hz: float = 5.0
    ) -> None:
        self._sos = butter(
            2, [lowcut_hz, highcut_hz], btype="bandpass", fs=sample_rate_hz, output="sos"
        )
        self._zi = np.zeros((self._sos.shape[0], 2), dtype=np.float64)

    def process(self, samples: FloatArray) -> FloatArray:
        values = np.asarray(samples, dtype=np.float32).reshape(-1)
        if values.size == 0:
            return values
        filtered, self._zi = sosfilt(self._sos, values, zi=self._zi)
        return np.asarray(filtered, dtype=np.float32)

    def reset(self) -> None:
        self._zi.fill(0)


class AdaptivePeakDetector:
    """Small Elgendi-inspired detector with bounded history and refractory control."""

    def __init__(self, sample_rate_hz: float) -> None:
        self._sample_rate_hz = sample_rate_hz
        self._history = deque[float](maxlen=max(round(sample_rate_hz * 3), 1))
        self._last_peak_index = -(10**12)
        self._refractory_samples = round(sample_rate_hz * 0.3)
        self._history_start_index = 0
        self._initialized = False

    def reset(self) -> None:
        self._history.clear()
        self._last_peak_index = -(10**12)
        self._initialized = False

    def process(
        self, samples: FloatArray, first_sample_index: int
    ) -> tuple[int, ...]:
        values = np.asarray(samples, dtype=np.float32).reshape(-1)
        if values.size == 0:
            return ()
        if not self._initialized:
            self._history_start_index = first_sample_index
            self._initialized = True
        elif first_sample_index != self._history_start_index + len(self._history):
            self.reset()
            self._history_start_index = first_sample_index
            self._initialized = True
        self._history.extend(float(value) for value in values)
        history = np.asarray(self._history, dtype=np.float32)
        # Squaring emphasizes the systolic pulse while retaining a very small detector state.
        energy = np.square(np.maximum(history, 0.0))
        threshold = float(np.median(energy) + 0.35 * np.std(energy))
        candidates, _ = find_peaks(
            energy,
            height=max(threshold, np.finfo(np.float32).eps),
            distance=max(self._refractory_samples, 1),
            prominence=max(float(np.std(energy)) * 0.2, np.finfo(np.float32).eps),
        )
        emitted: list[int] = []
        safe_end = first_sample_index + values.size - self._refractory_samples
        for candidate in candidates:
            global_index = self._history_start_index + int(candidate)
            if global_index <= self._last_peak_index or global_index > safe_end:
                continue
            self._last_peak_index = global_index
            emitted.append(global_index)
        self._history_start_index = first_sample_index + values.size - len(self._history)
        return tuple(emitted)


@dataclass(frozen=True, slots=True)
class Interval:
    """One peak-to-peak interval with an artifact decision."""

    end_sample_index: int
    duration_ms: float
    valid: bool


class IntervalRejector:
    """Reject physiologically implausible or locally anomalous intervals."""

    def __init__(self, sample_rate_hz: float) -> None:
        self._sample_rate_hz = sample_rate_hz
        self._previous_peak: int | None = None
        self._recent_valid: deque[float] = deque(maxlen=11)

    def reset(self) -> None:
        self._previous_peak = None
        self._recent_valid.clear()

    def process(self, peaks: tuple[int, ...]) -> tuple[Interval, ...]:
        result: list[Interval] = []
        for peak in peaks:
            previous = self._previous_peak
            self._previous_peak = peak
            if previous is None:
                continue
            duration_ms = (peak - previous) * 1_000.0 / self._sample_rate_hz
            valid = 300.0 <= duration_ms <= 2_000.0 and self._locally_plausible(duration_ms)
            result.append(Interval(peak, duration_ms, valid))
            if valid:
                self._recent_valid.append(duration_ms)
        return tuple(result)

    def _locally_plausible(self, value: float) -> bool:
        if len(self._recent_valid) < 3:
            return True
        values = np.asarray(self._recent_valid, dtype=float)
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))
        tolerance = max(0.2 * median, 3.0 * 1.4826 * mad)
        return abs(value - median) <= tolerance
