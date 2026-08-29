"""Single-loop orchestration for replay or live PPG processing."""

from __future__ import annotations

import argparse
import asyncio
import math
from collections import deque
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import aclosing, suppress
from dataclasses import dataclass
from pathlib import Path
from time import monotonic_ns
from typing import Protocol, cast, runtime_checkable

import numpy as np

from .acquisition import BleakSampleSource, SampleSource
from .config import RuntimeConfig
from .features import FeatureSnapshot, extract_features
from .fusion import BoundedOutputSink, OutputSink, UnixDatagramSink
from .model import LogisticModel
from .protocol import PacketTracker
from .quality import assess_quality
from .signal import (
    AdaptivePeakDetector,
    FloatArray,
    FloatRingBuffer,
    Interval,
    IntervalRejector,
    StreamingBandpass,
)
from .types import Channel, PpgFrame, QualityReason, QualityState, SensorStatus

SCHEMA_VERSION = 2

STATE_WARMUP = "WARMUP"
STATE_VALID = "VALID"
STATE_DEGRADED = "DEGRADED"
STATE_STALE = "STALE"

#: Returns a monotonic timestamp in nanoseconds; injected so tests can freeze it.
Clock = Callable[[], int]

#: Awaits the next queued frame with a timeout, raising ``TimeoutError`` when it
#: expires. Defaults to :func:`asyncio.wait_for`; tests inject a virtual-time
#: implementation so no test ever sleeps against the wall clock.
FrameWaiter = Callable[[Awaitable["PpgFrame | None"], float], Awaitable["PpgFrame | None"]]


@runtime_checkable
class SourceHealth(Protocol):
    """Optional transport diagnostics a :class:`SampleSource` may expose.

    A source that implements ``health()`` owns the transport counters reported
    in the ``session`` output block. Recognised keys are ``decode_errors``,
    ``queue_depth``, and ``queue_high_water``; any missing key falls back to the
    service-side value. Sources that do not implement this protocol report zero
    decode errors and the service's own ingest-queue depth.
    """

    def health(self) -> Mapping[str, int]:
        """Return transport counters for the current session."""


@dataclass(frozen=True, slots=True)
class _PacketRecord:
    """One accepted packet's contribution to the rolling feature window."""

    end_index: int
    received_samples: int
    lost_samples: int
    status: SensorStatus


class PhysiologyService:
    """Process a source incrementally with bounded state and no worker processes."""

    def __init__(
        self,
        source: SampleSource,
        sink: OutputSink,
        config: RuntimeConfig | None = None,
        model: LogisticModel | None = None,
        *,
        clock: Clock = monotonic_ns,
        wait_for: FrameWaiter = asyncio.wait_for,
        stale_after_seconds: float = 2.0,
        queue_maxsize: int = 64,
        time_driven: bool = True,
    ) -> None:
        config = RuntimeConfig() if config is None else config
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        if queue_maxsize <= 0:
            raise ValueError("queue_maxsize must be positive")
        self._source = source
        self._sink = sink
        self._config = config
        self._model = model
        self._clock = clock
        self._wait_for = wait_for
        self._stale_after_seconds = stale_after_seconds
        self._queue_maxsize = queue_maxsize
        self._time_driven = time_driven
        self._tracker = PacketTracker()
        self._filter = StreamingBandpass(
            config.sample_rate_hz, config.filter.lowcut_hz, config.filter.highcut_hz
        )
        self._detector = AdaptivePeakDetector(config.sample_rate_hz)
        self._rejector = IntervalRejector(config.sample_rate_hz)
        self._raw = FloatRingBuffer(config.raw_buffer_samples)
        self._intervals: deque[Interval] = deque()
        self._records: deque[_PacketRecord] = deque()
        self._last_hr_emit_index: int | None = None
        self._last_feature_emit_index: int | None = None
        self._session_origin: int | None = None
        self._last_end_index = 0
        self._last_frame_ns: int | None = None
        self._session_id = 0
        self._packets_received = 0
        self._duplicates = 0
        self._reordered = 0
        self._sequence_gaps = 0
        self._sample_rate_mismatches = 0
        self._queue: asyncio.Queue[PpgFrame | None] | None = None
        self._queue_high_water = 0
        self._source_error: BaseException | None = None

    @property
    def sample_rate_mismatches(self) -> int:
        """Return frames dropped because their sample rate did not match the config."""

        return self._sample_rate_mismatches

    async def run(self) -> None:
        """Run until the asynchronous source ends."""

        if self._time_driven:
            await self._run_time_driven()
        else:
            await self._run_frame_driven()

    async def _run_frame_driven(self) -> None:
        """Legacy path retained behind ``time_driven=False`` for regression recovery."""

        async with aclosing(self._frame_stream()) as frames:
            async for frame in frames:
                await self._process_frame(frame)

    async def _run_time_driven(self) -> None:
        """Tick on a timeout so a silent source still produces a state, not silence."""

        queue: asyncio.Queue[PpgFrame | None] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._queue = queue
        pump = asyncio.create_task(self._pump(queue))
        try:
            while True:
                try:
                    frame = await self._wait_for(queue.get(), self._stale_after_seconds)
                except TimeoutError:
                    await self._emit_tick(stale=True)
                    continue
                if frame is None:
                    break
                self._queue_high_water = max(self._queue_high_water, queue.qsize())
                await self._process_frame(frame)
        finally:
            pump.cancel()
            with suppress(asyncio.CancelledError):
                await pump
        error = self._source_error
        if error is not None:
            await self._emit_tick(stale=True)
            raise error

    async def _pump(self, queue: asyncio.Queue[PpgFrame | None]) -> None:
        """Feed frames into a bounded queue, recording rather than losing a failure."""

        try:
            async with aclosing(self._frame_stream()) as frames:
                async for frame in frames:
                    await queue.put(frame)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._source_error = error
        await queue.put(None)

    def _frame_stream(self) -> AsyncGenerator[PpgFrame, None]:
        """Return the source stream as a closable generator.

        ``aclosing`` guarantees ``stop_notify`` and the BLE disconnect run when the
        loop exits by exception, instead of waiting for garbage collection.
        """

        return cast("AsyncGenerator[PpgFrame, None]", self._source.frames())

    async def _process_frame(self, frame: PpgFrame) -> None:
        packet = frame.packet
        if frame.sample_rate_hz != round(self._config.sample_rate_hz):
            self._sample_rate_mismatches += 1
            return
        self._last_frame_ns = self._clock()
        self._packets_received += 1
        observation = self._tracker.observe(packet)
        self._session_id = observation.session_id
        if observation.duplicate:
            self._duplicates += 1
            return
        if observation.reordered:
            self._reordered += 1
            return
        self._sequence_gaps += observation.sequence_gap
        if self._session_origin is None:
            self._session_origin = packet.first_sample_index
        if observation.sample_gap or observation.reset_detected:
            self._reset_signal_state()
            self._rebase_emit_indices(packet.first_sample_index)
        if observation.reset_detected:
            self._session_origin = packet.first_sample_index
            self._records.clear()
        samples = _select_primary_channel(packet.channels, packet.samples)
        self._raw.append(samples)
        filtered = self._filter.process(samples)
        peaks = self._detector.process(filtered, packet.first_sample_index)
        self._intervals.extend(self._rejector.process(peaks))
        end_index = packet.first_sample_index + packet.sample_count
        self._last_end_index = end_index
        self._records.append(
            _PacketRecord(
                end_index=end_index,
                received_samples=int(samples.size),
                lost_samples=observation.sample_gap,
                status=packet.status,
            )
        )
        self._trim_window(end_index)
        await self._emit_if_due(end_index)

    def _reset_signal_state(self) -> None:
        self._filter.reset()
        self._detector.reset()
        self._rejector.reset()
        self._intervals.clear()

    def _rebase_emit_indices(self, origin: int) -> None:
        """Clamp emit bookkeeping to a restarted sample-index origin.

        An MCU reset restarts ``first_sample_index`` at zero. Without this the
        emit tests stay negative until the index catches up, which silenced the
        service for as long as it had been running.
        """

        if self._last_hr_emit_index is not None:
            self._last_hr_emit_index = min(self._last_hr_emit_index, origin)
        if self._last_feature_emit_index is not None:
            self._last_feature_emit_index = min(self._last_feature_emit_index, origin)

    def _window_samples(self) -> int:
        return round(self._config.feature_window_seconds * self._config.sample_rate_hz)

    def _trim_window(self, end_index: int) -> None:
        oldest = end_index - self._window_samples()
        while self._intervals and self._intervals[0].end_sample_index < oldest:
            self._intervals.popleft()
        while self._records and self._records[0].end_index < oldest:
            self._records.popleft()

    def _packet_loss_fraction(self) -> float:
        """Return loss over the feature window only, so an old gap eventually clears."""

        lost = sum(record.lost_samples for record in self._records)
        received = sum(record.received_samples for record in self._records)
        return lost / max(received + lost, 1)

    def _window_status(self) -> SensorStatus:
        """Return the union of sensor status across the window, not just the last packet."""

        status = SensorStatus.NONE
        for record in self._records:
            status |= record.status
        return status

    async def _emit_if_due(self, end_index: int) -> None:
        hr_period = round(self._config.hr_update_seconds * self._config.sample_rate_hz)
        feature_period = round(self._config.feature_update_seconds * self._config.sample_rate_hz)
        hr_due = (
            self._last_hr_emit_index is None or end_index - self._last_hr_emit_index >= hr_period
        )
        feature_due = (
            self._last_feature_emit_index is None
            or end_index - self._last_feature_emit_index >= feature_period
        )
        if not hr_due and not feature_due:
            return
        if hr_due:
            self._last_hr_emit_index = end_index
        if feature_due:
            self._last_feature_emit_index = end_index
        await self._sink.publish(self._output(end_index, feature_due=feature_due, stale=False))

    async def _emit_tick(self, *, stale: bool) -> None:
        await self._sink.publish(
            self._output(self._last_end_index, feature_due=False, stale=stale)
        )

    def _output(
        self, end_index: int, *, feature_due: bool, stale: bool
    ) -> dict[str, object]:
        window_samples = self._window_samples()
        origin = 0 if self._session_origin is None else self._session_origin
        warmup = end_index - origin < window_samples
        features = None if warmup else extract_features(tuple(self._intervals))
        artifact_fraction = features.artifact_fraction if features is not None else 1.0
        quality = assess_quality(
            self._raw.latest(window_samples),
            packet_loss_fraction=self._packet_loss_fraction(),
            artifact_fraction=artifact_fraction,
            valid_interval_count=0 if features is None else features.valid_interval_count,
            status=self._window_status(),
            config=self._config.quality,
        )
        probability, model_reason = self._fatigue_probability(
            features, quality.state, predict=feature_due and not stale and not warmup
        )
        if stale:
            state = STATE_STALE
        elif warmup:
            state = STATE_WARMUP
        elif quality.state is QualityState.GOOD:
            state = STATE_VALID
        else:
            state = STATE_DEGRADED
        return {
            "schema_version": SCHEMA_VERSION,
            "model_version": None if self._model is None else self._model.version,
            "monotonic_ns": self._clock(),
            "window_end_sample_index": end_index,
            "state": state,
            "feature_due": feature_due,
            "mean_hr_bpm": None if features is None else _finite(features.mean_hr_bpm),
            "features": None if features is None else _feature_payload(features),
            "quality": {
                "state": quality.state.value,
                "score": quality.score,
                "reasons": int(quality.reasons | model_reason),
                "packet_loss_fraction": quality.packet_loss_fraction,
                "artifact_fraction": quality.artifact_fraction,
                "clipping_fraction": quality.clipping_fraction,
                "valid_interval_count": quality.valid_interval_count,
            },
            "fatigue_probability": probability,
            "session": self._session_payload(),
        }

    def _session_payload(self) -> dict[str, object]:
        health = self._source_health()
        queue = self._queue
        last_frame_ns = self._last_frame_ns
        return {
            "session_id": self._session_id,
            "packets_received": self._packets_received,
            "decode_errors": health.get("decode_errors", 0),
            "duplicates": self._duplicates,
            "reordered": self._reordered,
            "sequence_gaps": self._sequence_gaps,
            "queue_depth": health.get("queue_depth", 0 if queue is None else queue.qsize()),
            "queue_high_water": health.get("queue_high_water", self._queue_high_water),
            "dropped_outputs": _int_attribute(self._sink, "dropped_outputs"),
            "last_frame_age_seconds": (
                None if last_frame_ns is None else (self._clock() - last_frame_ns) / 1e9
            ),
        }

    def _source_health(self) -> Mapping[str, int]:
        source = self._source
        if isinstance(source, SourceHealth):
            return source.health()
        return {}

    def _fatigue_probability(
        self,
        features: FeatureSnapshot | None,
        quality: QualityState,
        *,
        predict: bool,
    ) -> tuple[float | None, QualityReason]:
        """Return a probability and any model-input reason, never raising.

        A degenerate window can make ``cvnn`` or ``hr_slope`` non-finite, and the
        model raises on such input. Losing acquisition and HR because of one NaN
        is never an acceptable trade for a driver-monitoring service.
        """

        if features is None:
            return None, QualityReason.NONE
        try:
            values = features.model_features()
            finite = all(math.isfinite(value) for value in values.values())
        except (TypeError, ValueError):
            return None, QualityReason.MODEL_INPUT
        if not finite:
            return None, QualityReason.MODEL_INPUT
        if not predict or self._model is None or quality is QualityState.BAD:
            return None, QualityReason.NONE
        try:
            return self._model.probability(values), QualityReason.NONE
        except (TypeError, ValueError):
            return None, QualityReason.MODEL_INPUT


def _int_attribute(source: object, name: str) -> int:
    value = getattr(source, name, 0)
    return value if isinstance(value, int) else 0


def _finite(value: float) -> float | None:
    """Map a non-finite float to ``None`` so ``allow_nan=False`` cannot break the sink."""

    return value if math.isfinite(value) else None


def _select_primary_channel(
    channels: Channel, rows: tuple[tuple[int, ...], ...]
) -> FloatArray:
    offset = 1 if channels == (Channel.RED | Channel.INFRARED) else 0
    return np.asarray([row[offset] for row in rows], dtype=np.float32)


def _feature_payload(features: FeatureSnapshot) -> dict[str, float | int | None]:
    return {
        "mean_hr_bpm": _finite(features.mean_hr_bpm),
        "hr_slope_bpm_per_min": _finite(features.hr_slope_bpm_per_min),
        "median_ibi_ms": _finite(features.median_ibi_ms),
        "rmssd_ms": _finite(features.rmssd_ms),
        "sdnn_ms": _finite(features.sdnn_ms),
        "pnn50": _finite(features.pnn50),
        "cvnn": _finite(features.cvnn),
        "valid_interval_count": features.valid_interval_count,
        "artifact_fraction": _finite(features.artifact_fraction),
    }


async def _run(source: SampleSource, sink: UnixDatagramSink, model: LogisticModel | None) -> None:
    bounded = BoundedOutputSink(sink)
    try:
        await PhysiologyService(source, bounded, model=model).run()
    finally:
        await bounded.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ble-address", required=True)
    parser.add_argument("--characteristic", required=True)
    parser.add_argument("--socket", type=Path, default=Path("/run/dms-physiology.sock"))
    parser.add_argument("--model", type=Path)
    args = parser.parse_args()
    model = None if args.model is None else LogisticModel.from_json_file(args.model)
    sink = UnixDatagramSink(args.socket)
    source = BleakSampleSource(args.ble_address, args.characteristic, sample_rate_hz=100)
    try:
        asyncio.run(_run(source, sink, model))
    finally:
        sink.close()


if __name__ == "__main__":
    main()
