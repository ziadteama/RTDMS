"""Virtual-time coverage for the v2 output state machine and session health."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import replace

import pytest
from conftest import (
    FixedClock,
    HealthySource,
    ScriptedSource,
    fixed_clock,
    frames_with_gap,
    frames_with_reset,
    virtual_wait_for,
)

from dms_physiology.acquisition import ReplaySource
from dms_physiology.config import RuntimeConfig
from dms_physiology.fusion import BoundedOutputSink, InMemorySink
from dms_physiology.service import (
    SCHEMA_VERSION,
    STATE_DEGRADED,
    STATE_STALE,
    STATE_VALID,
    STATE_WARMUP,
    PhysiologyService,
)
from dms_physiology.simulate import synthetic_frames
from dms_physiology.types import PpgFrame, QualityReason, SensorStatus

SAMPLE_RATE_HZ = 100


def build(
    source: object,
    sink: object,
    *,
    model: object = None,
    time_driven: bool = True,
    clock: FixedClock | None = None,
) -> PhysiologyService:
    return PhysiologyService(
        source,  # type: ignore[arg-type]
        sink,  # type: ignore[arg-type]
        RuntimeConfig(),
        model,  # type: ignore[arg-type]
        clock=fixed_clock() if clock is None else clock,
        wait_for=virtual_wait_for,
        time_driven=time_driven,
    )


def states(sink: InMemorySink) -> list[str]:
    return [str(output["state"]) for output in sink.outputs]


def session(output: Mapping[str, object]) -> Mapping[str, object]:
    block = output["session"]
    assert isinstance(block, Mapping)
    return block


# --- WP-4.1 / 4.6 state machine -------------------------------------------------


async def test_warmup_then_valid() -> None:
    sink = InMemorySink()
    await build(ReplaySource(synthetic_frames(90)), sink).run()

    observed = states(sink)
    assert observed[0] == STATE_WARMUP
    assert STATE_VALID in observed
    assert observed.index(STATE_VALID) > observed.count(STATE_WARMUP) - 1
    assert set(observed) <= {STATE_WARMUP, STATE_VALID, STATE_DEGRADED}


async def test_valid_degrades_on_loss_then_recovers() -> None:
    sink = InMemorySink()
    # Drop five frames (100 samples) at t=120 s, then replay long enough for the
    # loss to age out of the rolling 60 s window.
    await build(ReplaySource(frames_with_gap(200, 6000, 5)), sink).run()

    observed = states(sink)
    first_valid = observed.index(STATE_VALID)
    degraded = observed.index(STATE_DEGRADED, first_valid)
    assert STATE_VALID in observed[degraded:]


async def test_silence_becomes_stale() -> None:
    sink = InMemorySink()
    source = ScriptedSource([*synthetic_frames(90), 200])
    await build(source, sink).run()

    assert STATE_STALE in states(sink)
    assert states(sink).index(STATE_STALE) > states(sink).index(STATE_VALID)
    assert source.closed


async def test_stale_returns_to_warmup_after_reconnect_with_reset() -> None:
    sink = InMemorySink()
    before, after = synthetic_frames(90), synthetic_frames(20)
    first = after[0]
    restarted = replace(first, packet=replace(first.packet, status=SensorStatus.SENSOR_RESET))
    source = ScriptedSource([*before, 200, restarted, *after[1:]])
    await build(source, sink).run()

    observed = states(sink)
    stale = observed.index(STATE_STALE)
    assert STATE_WARMUP in observed[stale:]


async def test_bad_quality_is_reported_in_quality_not_in_state() -> None:
    sink = InMemorySink()
    frames = synthetic_frames(90)
    faulted = tuple(
        replace(frame, packet=replace(frame.packet, status=SensorStatus.CONTACT_LOST))
        if 7000 <= frame.packet.first_sample_index < 7100
        else frame
        for frame in frames
    )
    await build(ReplaySource(faulted), sink).run()

    bad = [output for output in sink.outputs if output["quality"]["state"] == "bad"]  # type: ignore[index]
    assert bad
    assert all(output["state"] != "bad" for output in sink.outputs)
    assert all(output["state"] in {STATE_WARMUP, STATE_VALID, STATE_DEGRADED} for output in bad)
    assert all(output["fatigue_probability"] is None for output in bad)


# --- WP-4.5 sticky sensor status ------------------------------------------------


async def test_sensor_fault_marks_the_whole_window_not_one_packet() -> None:
    sink = InMemorySink()
    frames = synthetic_frames(90)
    faulted = tuple(
        replace(frame, packet=replace(frame.packet, status=SensorStatus.CONTACT_LOST))
        if frame.packet.first_sample_index == 7000
        else frame
        for frame in frames
    )
    await build(ReplaySource(faulted), sink).run()

    flagged = [
        output
        for output in sink.outputs
        if int(output["quality"]["reasons"]) & QualityReason.SENSOR_FAULT  # type: ignore[index]
    ]
    # One faulted packet covers 0.2 s; a per-packet status would flag at most one
    # output, while the window contract flags every output for the next 60 s.
    assert len(flagged) > 30


# --- WP-2 loss accounting and post-reset rebasing -------------------------------


async def test_reset_emits_again_within_one_second_of_sample_time() -> None:
    sink = InMemorySink()
    await build(ReplaySource(frames_with_reset(90, 20)), sink).run()

    after_reset = [
        output
        for output in sink.outputs
        if int(session(output)["session_id"]) > 0  # type: ignore[call-overload]
    ]
    assert after_reset
    assert int(after_reset[0]["window_end_sample_index"]) <= SAMPLE_RATE_HZ


async def test_packet_loss_fraction_is_a_rolling_window() -> None:
    sink = InMemorySink()
    await build(ReplaySource(frames_with_gap(200, 6000, 5)), sink).run()

    losses = [float(output["quality"]["packet_loss_fraction"]) for output in sink.outputs]  # type: ignore[index]
    assert max(losses) > 0.0
    # A lifetime fraction can only decay asymptotically; a rolling one returns to
    # exactly zero once the gap leaves the window.
    assert losses[-1] == 0.0


async def test_sample_rate_mismatch_is_counted_not_raised() -> None:
    sink = InMemorySink()
    frames = synthetic_frames(90)
    mixed = (replace(frames[0], sample_rate_hz=125), *frames[1:])
    service = build(ReplaySource(mixed), sink)
    await service.run()

    assert service.sample_rate_mismatches == 1
    assert STATE_VALID in states(sink)


# --- WP-3 single publish, injectable clock, schema v2 ---------------------------


async def test_exactly_one_publish_per_window_end_index() -> None:
    sink = InMemorySink()
    await build(ReplaySource(synthetic_frames(90)), sink).run()

    indices = [output["window_end_sample_index"] for output in sink.outputs]
    assert len(indices) == len(set(indices))
    assert any(output["feature_due"] is True for output in sink.outputs)
    assert any(output["feature_due"] is False for output in sink.outputs)
    assert all(output["schema_version"] == SCHEMA_VERSION for output in sink.outputs)


async def test_fixed_clock_makes_two_runs_byte_identical() -> None:
    async def run_once() -> str:
        sink = InMemorySink()
        await build(ReplaySource(synthetic_frames(90)), sink).run()
        return json.dumps(sink.outputs, sort_keys=True, allow_nan=False)

    assert await run_once() == await run_once()


async def test_features_and_quality_run_once_per_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dms_physiology.service as service_module

    calls = {"features": 0, "quality": 0}
    real_features = service_module.extract_features
    real_quality = service_module.assess_quality

    def counting_features(*args: object, **kwargs: object) -> object:
        calls["features"] += 1
        return real_features(*args, **kwargs)  # type: ignore[arg-type]

    def counting_quality(*args: object, **kwargs: object) -> object:
        calls["quality"] += 1
        return real_quality(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service_module, "extract_features", counting_features)
    monkeypatch.setattr(service_module, "assess_quality", counting_quality)

    sink = InMemorySink()
    await build(ReplaySource(synthetic_frames(90)), sink).run()

    assert calls["quality"] == len(sink.outputs)
    assert calls["features"] <= len(sink.outputs)


# --- WP-4.8 frame-driven fallback ----------------------------------------------


async def test_frame_driven_path_matches_the_time_driven_path() -> None:
    clock = fixed_clock()
    frame_sink, time_sink = InMemorySink(), InMemorySink()
    legacy = build(ReplaySource(synthetic_frames(90)), frame_sink, clock=clock, time_driven=False)
    await legacy.run()
    await build(ReplaySource(synthetic_frames(90)), time_sink, clock=clock).run()

    assert frame_sink.outputs == time_sink.outputs


# --- WP-5 robustness ------------------------------------------------------------


class _NanModel:
    version = "nan-test"

    def probability(self, features: Mapping[str, float]) -> float:
        raise ValueError("missing or non-finite model feature: cvnn")


async def test_model_failure_suppresses_probability_and_flags_model_input() -> None:
    sink = InMemorySink()
    await build(ReplaySource(synthetic_frames(90)), sink, model=_NanModel()).run()

    flagged = [
        output
        for output in sink.outputs
        if int(output["quality"]["reasons"]) & QualityReason.MODEL_INPUT  # type: ignore[index]
    ]
    assert flagged
    assert all(output["fatigue_probability"] is None for output in sink.outputs)


class _BrokenSink:
    def __init__(self) -> None:
        self.attempts = 0

    async def publish(self, output: Mapping[str, object]) -> None:
        self.attempts += 1
        raise FileNotFoundError("nothing bound the socket")


async def test_bounded_sink_never_propagates_and_counts_failures() -> None:
    broken = _BrokenSink()
    bounded = BoundedOutputSink(broken, maxsize=4)
    await build(ReplaySource(synthetic_frames(70)), bounded).run()
    for _ in range(50):
        await asyncio.sleep(0)
    await bounded.aclose()

    assert broken.attempts > 0
    assert bounded.sink_errors == broken.attempts


async def test_bounded_sink_drops_when_full() -> None:
    class _StalledSink:
        async def publish(self, output: Mapping[str, object]) -> None:
            await asyncio.Event().wait()

    bounded = BoundedOutputSink(_StalledSink(), maxsize=2)
    for index in range(10):
        await bounded.publish({"index": index})
    await bounded.aclose()

    assert bounded.dropped_outputs > 0
    assert bounded.queue_depth <= 2


async def test_source_failure_emits_a_state_before_propagating() -> None:
    class _FailingSource:
        async def frames(self) -> AsyncIterator[PpgFrame]:
            for frame in synthetic_frames(70):
                yield frame
            raise RuntimeError("BLE link dropped")

    sink = InMemorySink()
    with pytest.raises(RuntimeError, match="BLE link dropped"):
        await build(_FailingSource(), sink).run()

    assert states(sink)[-1] == STATE_STALE


async def test_source_generator_is_closed_when_the_loop_fails() -> None:
    class _ExplodingSink:
        async def publish(self, output: Mapping[str, object]) -> None:
            raise RuntimeError("sink exploded")

    source = ScriptedSource(list(synthetic_frames(5)))
    with pytest.raises(RuntimeError, match="sink exploded"):
        await build(source, _ExplodingSink()).run()

    assert source.closed


# --- WP-5.9 session health ------------------------------------------------------


async def test_session_block_reports_all_ten_fields() -> None:
    sink = InMemorySink()
    await build(ReplaySource(frames_with_gap(90, 3000, 5)), sink).run()

    block = session(sink.outputs[-1])
    assert set(block) == {
        "packets_received",
        "decode_errors",
        "duplicates",
        "reordered",
        "sequence_gaps",
        "queue_depth",
        "queue_high_water",
        "dropped_outputs",
        "session_id",
        "last_frame_age_seconds",
    }
    assert int(block["packets_received"]) > 0  # type: ignore[call-overload]
    assert int(block["sequence_gaps"]) == 5  # type: ignore[call-overload]
    assert block["last_frame_age_seconds"] == 0.0


async def test_duplicates_and_reordering_are_counted() -> None:
    sink = InMemorySink()
    frames = list(synthetic_frames(70))
    frames.insert(100, frames[99])
    await build(ReplaySource(frames), sink).run()

    assert int(session(sink.outputs[-1])["duplicates"]) == 1  # type: ignore[call-overload]


async def test_source_health_overrides_transport_counters() -> None:
    sink = InMemorySink()
    health = {"decode_errors": 3, "queue_depth": 7, "queue_high_water": 9}
    await build(HealthySource(synthetic_frames(70), health), sink).run()

    block = session(sink.outputs[-1])
    assert block["decode_errors"] == 3
    assert block["queue_depth"] == 7
    assert block["queue_high_water"] == 9


async def test_dropped_outputs_are_read_from_the_sink() -> None:
    class _CountingSink(InMemorySink):
        dropped_outputs = 11

    sink = _CountingSink()
    await build(ReplaySource(synthetic_frames(70)), sink).run()

    assert session(sink.outputs[-1])["dropped_outputs"] == 11
