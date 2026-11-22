from unittest.mock import patch

import pytest
from dms_physiology.garmin_rr import RrPacket, encode

from rtdms_pi.garmin_source import GarminPhysioSource
from rtdms_pi.health import HealthProbe
from rtdms_pi.payloads import health_payload


def packet(seq, *, version=2, motion=0, ack=False, watch_ms=None):
    return encode(
        RrPacket(
            seq,
            seq * 1000 if watch_ms is None else watch_ms,
            75,
            (800,),
            version=version,
            motion=motion,
            contact=True,
            ack=ack,
            echo_seq=7,
        )
    )


@pytest.mark.parametrize("version", [1, 2])
def test_packets_and_stale(clock, version) -> None:
    source = GarminPhysioSource(clock=clock)
    assert source.latest() is None
    source.handle_write(b"invalid")
    source.handle_write(packet(1, version=version))
    report = source.latest()
    assert source.decode_errors == 1
    assert report.t == clock()
    assert report.raw["hr_bpm"] == 75
    assert report.raw["quality"] == "degraded"
    assert report.raw["worn"] == (True if version == 2 else None)
    assert report.raw["rr_ms"] == (800,)
    assert report.raw["ack_age_s"] is None
    assert "fatigue_probability" not in report.raw
    if version == 1:
        assert report.raw["motion"] is report.raw["wrist_still_s"] is None
    clock.advance(10.001)
    assert source.latest() is None


def test_caching_and_rejected_frames(clock) -> None:
    source = GarminPhysioSource(clock=clock)
    source.handle_write(packet(2))
    with (
        patch.object(source._hr, "snapshot", wraps=source._hr.snapshot) as hr,
        patch.object(source._hrv, "compute", wraps=source._hrv.compute) as hrv,
    ):
        first = source.latest()
        source.handle_write(packet(2))
        source.handle_write(packet(1))
        assert source.tracker.duplicates == source.tracker.late == 1
        clock.advance(0.5)
        source.handle_write(packet(3))
        assert source.latest() is first
        assert hr.call_count == hrv.call_count == 1
        clock.advance(0.5)
        assert source.latest() is not first
        assert hr.call_count == 2 and hrv.call_count == 1
        clock.advance(4)
        source.latest()
        assert hr.call_count == 3 and hrv.call_count == 2


def test_buffered_burst_and_motion_ack(clock) -> None:
    source = GarminPhysioSource(clock=clock)
    source.handle_write(packet(1, motion=40, ack=True))
    clock.advance(10)
    with (
        patch.object(source._hr, "add", wraps=source._hr.add) as hr,
        patch.object(source._hrv, "add", wraps=source._hrv.add) as hrv,
    ):
        for seq in range(2, 5):
            source.handle_write(packet(seq))
        assert [c.args[1] for c in hr.call_args_list] == [101, 102, 103]
        assert [c.args[0].rx_monotonic for c in hrv.call_args_list] == [101, 102, 103]
    report = source.latest()
    assert report.t == 103
    assert report.raw["quality"] == "bad"  # buffered data is not live HR
    assert report.raw["wrist_still_s"] == report.raw["ack_age_s"] == 10
    assert report.raw["echo_seq"] == 7
    assert source.diagnostics() == {"watch_offset_spread_ms": 9000, "late_packets": 3}
    clock.advance(1)
    source.handle_write(packet(5, motion=50, ack=True, watch_ms=12000))
    assert source.latest().raw["wrist_still_s"] == 0
    assert source.latest().raw["ack_age_s"] == 0
    clock.advance(1)
    source.handle_write(packet(0, version=1, watch_ms=0))
    assert source.latest().raw["wrist_still_s"] is None
    assert source.latest().raw["ack_age_s"] is None


def test_health_diagnostics(clock) -> None:
    from test_payloads import validate

    source = GarminPhysioSource(clock=clock)
    source.handle_write(packet(1))
    payload = health_payload(
        cpu_pct=0,
        fps=0,
        uptime_s=1,
        camera=False,
        models={},
        physio_diag=source.diagnostics(),
    )
    validate("health", payload)
    diag = payload["physio_diag"]
    assert diag["shadow_agree"] is diag["shadow_disagree"] is diag["shadow_only"] is None
    probe = HealthProbe(physio_source=source, run=lambda *a, **kw: "", read_text=lambda p: "")
    actual = probe.probe()
    validate("health", actual)
    assert actual["physio_diag"] == diag
