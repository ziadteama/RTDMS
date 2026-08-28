"""Single-loop orchestration for replay or live PPG processing."""

from __future__ import annotations

import argparse
import asyncio
from collections import deque
from pathlib import Path
from time import monotonic_ns

import numpy as np

from .acquisition import BleakSampleSource, SampleSource
from .config import RuntimeConfig
from .features import FeatureSnapshot, extract_features
from .fusion import OutputSink, UnixDatagramSink
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
from .types import Channel, QualityState, SensorStatus


class PhysiologyService:
    """Process a source incrementally with bounded state and no worker processes."""

    def __init__(
        self,
        source: SampleSource,
        sink: OutputSink,
        config: RuntimeConfig | None = None,
        model: LogisticModel | None = None,
    ) -> None:
        config = RuntimeConfig() if config is None else config
        self._source = source
        self._sink = sink
        self._config = config
        self._model = model
        self._tracker = PacketTracker()
        self._filter = StreamingBandpass(
            config.sample_rate_hz, config.filter.lowcut_hz, config.filter.highcut_hz
        )
        self._detector = AdaptivePeakDetector(config.sample_rate_hz)
        self._rejector = IntervalRejector(config.sample_rate_hz)
        self._raw = FloatRingBuffer(config.raw_buffer_samples)
        self._intervals: deque[Interval] = deque()
        self._total_samples = 0
        self._lost_samples = 0
        self._last_hr_emit_index: int | None = None
        self._last_feature_emit_index: int | None = None

    async def run(self) -> None:
        """Run until the asynchronous source ends."""

        async for frame in self._source.frames():
            packet = frame.packet
            if frame.sample_rate_hz != round(self._config.sample_rate_hz):
                raise ValueError("frame sample rate does not match RuntimeConfig")
            observation = self._tracker.observe(packet)
            if observation.duplicate or observation.reordered:
                continue
            if observation.sample_gap or observation.reset_detected:
                self._lost_samples += observation.sample_gap
                self._reset_signal_state()
            samples = _select_primary_channel(packet.channels, packet.samples)
            self._raw.append(samples)
            self._total_samples += samples.size
            filtered = self._filter.process(samples)
            peaks = self._detector.process(filtered, packet.first_sample_index)
            self._intervals.extend(self._rejector.process(peaks))
            end_index = packet.first_sample_index + packet.sample_count
            self._trim_intervals(end_index)
            await self._emit_if_due(end_index, packet.status)

    def _reset_signal_state(self) -> None:
        self._filter.reset()
        self._detector.reset()
        self._rejector.reset()
        self._intervals.clear()

    def _trim_intervals(self, end_index: int) -> None:
        oldest = end_index - round(
            self._config.feature_window_seconds * self._config.sample_rate_hz
        )
        while self._intervals and self._intervals[0].end_sample_index < oldest:
            self._intervals.popleft()

    async def _emit_if_due(self, end_index: int, status: SensorStatus) -> None:
        hr_period = round(self._config.hr_update_seconds * self._config.sample_rate_hz)
        feature_period = round(self._config.feature_update_seconds * self._config.sample_rate_hz)
        if self._last_hr_emit_index is None or end_index - self._last_hr_emit_index >= hr_period:
            self._last_hr_emit_index = end_index
            await self._sink.publish(self._output(end_index, status, feature_due=False))
        if (
            self._last_feature_emit_index is None
            or end_index - self._last_feature_emit_index >= feature_period
        ):
            self._last_feature_emit_index = end_index
            await self._sink.publish(self._output(end_index, status, feature_due=True))

    def _output(
        self, end_index: int, status: SensorStatus, *, feature_due: bool
    ) -> dict[str, object]:
        warmup_samples = round(self._config.feature_window_seconds * self._config.sample_rate_hz)
        features = extract_features(tuple(self._intervals)) if end_index >= warmup_samples else None
        artifact_fraction = features.artifact_fraction if features is not None else 1.0
        quality = assess_quality(
            self._raw.latest(
                round(self._config.feature_window_seconds * self._config.sample_rate_hz)
            ),
            packet_loss_fraction=self._lost_samples
            / max(self._total_samples + self._lost_samples, 1),
            artifact_fraction=artifact_fraction,
            valid_interval_count=0 if features is None else features.valid_interval_count,
            status=status,
            config=self._config.quality,
        )
        probability = self._fatigue_probability(features, quality.state) if feature_due else None
        state = "warmup" if features is None else quality.state.value
        return {
            "schema_version": 1,
            "model_version": None if self._model is None else self._model.version,
            "monotonic_ns": monotonic_ns(),
            "window_end_sample_index": end_index,
            "state": state,
            "mean_hr_bpm": None if features is None else features.mean_hr_bpm,
            "features": None if features is None else _feature_payload(features),
            "quality": {
                "state": quality.state.value,
                "score": quality.score,
                "reasons": int(quality.reasons),
                "packet_loss_fraction": quality.packet_loss_fraction,
                "artifact_fraction": quality.artifact_fraction,
                "clipping_fraction": quality.clipping_fraction,
                "valid_interval_count": quality.valid_interval_count,
            },
            "fatigue_probability": probability,
        }

    def _fatigue_probability(
        self, features: FeatureSnapshot | None, quality: QualityState
    ) -> float | None:
        if self._model is None or features is None or quality is QualityState.BAD:
            return None
        return self._model.probability(features.model_features())


def _select_primary_channel(
    channels: Channel, rows: tuple[tuple[int, ...], ...]
) -> FloatArray:
    offset = 1 if channels == (Channel.RED | Channel.INFRARED) else 0
    return np.asarray([row[offset] for row in rows], dtype=np.float32)


def _feature_payload(features: FeatureSnapshot) -> dict[str, float | int]:
    return {
        "mean_hr_bpm": features.mean_hr_bpm,
        "hr_slope_bpm_per_min": features.hr_slope_bpm_per_min,
        "median_ibi_ms": features.median_ibi_ms,
        "rmssd_ms": features.rmssd_ms,
        "sdnn_ms": features.sdnn_ms,
        "pnn50": features.pnn50,
        "cvnn": features.cvnn,
        "valid_interval_count": features.valid_interval_count,
        "artifact_fraction": features.artifact_fraction,
    }


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
        asyncio.run(PhysiologyService(source, sink, model=model).run())
    finally:
        sink.close()


if __name__ == "__main__":
    main()
