from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from rtdms_pi.incidents.ring import Entry, FrameRing
from rtdms_pi.incidents.sink import RingIncidentSink
from rtdms_pi.incidents.store import IncidentStore


class FakeScheduler:
    def __init__(self) -> None:
        self.scheduled: list[tuple[float, Callable[[], None]]] = []

    def __call__(self, delay_s: float, callback: Callable[[], None]) -> None:
        self.scheduled.append((delay_s, callback))

    def run_all(self) -> None:
        for _, cb in self.scheduled:
            cb()
        self.scheduled.clear()


def test_sink_report_mapping(tmp_path: Path) -> None:
    ring = FrameRing(seconds=30.0, fps=10.0)
    for i in range(250):
        t = 80.0 + i * 0.1
        ring.push(Entry(t_mono=t, t_wall=t, jpeg=b"\xff\xd8\xff\xd9", status={}, alert={}))

    store = IncidentStore(root=tmp_path)
    scheduler = FakeScheduler()
    sink = RingIncidentSink(
        ring=ring, store=store, transcoder=None, clock=lambda: 105.0, scheduler=scheduler
    )

    req = {"t_crash": 1732117202400, "g_peak": 5.5, "client_id": "c-uuid-1"}
    offset = -200
    inc_id = sink.report(req, clock_offset_ms=offset)
    assert inc_id == "2024-11-20T15-40-02-400Z"
    assert len(scheduler.scheduled) == 1
    assert "c-uuid-1" in sink._pending

    scheduler.run_all()
    # Pruned after snapshot completes
    assert "c-uuid-1" not in sink._pending
    inc_dir = tmp_path / inc_id
    assert inc_dir.is_dir()
    meta = json.loads((inc_dir / "meta.json").read_text())
    assert meta["clock_synced"] is True
    assert meta["client_id"] == "c-uuid-1"


def test_sink_idempotency_and_restart(tmp_path: Path) -> None:
    ring = FrameRing(seconds=30.0, fps=10.0)
    store = IncidentStore(root=tmp_path)
    scheduler = FakeScheduler()
    sink = RingIncidentSink(
        ring=ring, store=store, transcoder=None, clock=lambda: 105.0, scheduler=scheduler
    )

    req = {"t_crash": 1732117202400, "g_peak": 5.5, "client_id": "c-uuid-1"}
    inc_id = sink.report(req, clock_offset_ms=-200)
    # Deduplicates before callback runs
    assert sink.report(req, clock_offset_ms=-200) == inc_id
    assert len(scheduler.scheduled) == 1

    scheduler.run_all()
    assert "c-uuid-1" not in sink._pending

    # Survives restart on fresh store and sink
    new_store = IncidentStore(root=tmp_path)
    new_sink = RingIncidentSink(
        ring=ring, store=new_store, clock=lambda: 105.0, scheduler=scheduler
    )
    assert new_sink.report(req, clock_offset_ms=-200) == inc_id
    assert len(scheduler.scheduled) == 0


def test_sink_missing_clock_offset(tmp_path: Path) -> None:
    ring = FrameRing(seconds=30.0, fps=10.0)
    store = IncidentStore(root=tmp_path)
    scheduler = FakeScheduler()
    # Pi wall clock time is 1732117205.0
    sink = RingIncidentSink(
        ring=ring,
        store=store,
        clock=lambda: 1732117205.0,
        scheduler=scheduler,
    )

    req = {"t_crash": 1732117202400, "g_peak": 4.2, "client_id": "c-unsynced"}
    inc_id = sink.report(req, clock_offset_ms=None)
    scheduler.run_all()

    meta = json.loads((tmp_path / inc_id / "meta.json").read_text())
    assert meta["clock_synced"] is False


def test_sink_selects_frames_by_monotonic_time(tmp_path: Path) -> None:
    """Offset is pi_mono_ms - phone_ms, so the window must be found on t_mono, not t_wall."""
    ring = FrameRing(seconds=30.0, fps=10.0)
    for i in range(250):
        t_mono = 80.0 + i * 0.1
        ring.push(Entry(t_mono=t_mono, t_wall=1.79e9 + t_mono, jpeg=b"\xff\xd8\xff\xd9",
                        status={}, alert={}))
    store = IncidentStore(root=tmp_path)
    scheduler = FakeScheduler()
    sink = RingIncidentSink(ring=ring, store=store, clock=lambda: 103.0,
                            wall=lambda: 1.79e9 + 103.0, scheduler=scheduler)
    phone_crash_ms = 1795189202400
    offset = 100_000 - phone_crash_ms  # crash happened at Pi monotonic 100 s
    inc_id = sink.report({"t_crash": phone_crash_ms, "client_id": "c-mono"},
                         clock_offset_ms=offset)
    assert scheduler.scheduled[0][0] == 2.0  # waits until 5 s after the crash
    scheduler.run_all()
    lines = [ln for ln in (tmp_path / inc_id / "data.jsonl").read_text().splitlines() if ln]
    assert len(lines) > 200  # 20 s before + 5 s after at 10 fps, minus ring edges
    meta = json.loads((tmp_path / inc_id / "meta.json").read_text())
    assert meta["created"] == 1.79e9 + 103.0


def test_sink_without_crash_time_uses_wall_time_for_the_id(tmp_path: Path) -> None:
    ring = FrameRing(seconds=30.0, fps=10.0)
    sink = RingIncidentSink(ring=ring, store=IncidentStore(root=tmp_path), clock=lambda: 103.0,
                            wall=lambda: 1795189202.4, scheduler=FakeScheduler())
    assert sink.report({"client_id": "no-time"}) == "2026-11-20T15-40-02-400Z"
