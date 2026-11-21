from __future__ import annotations

import threading

from rtdms_pi.incidents.ring import Entry, FrameRing


def _make_entry(t_mono: float, t_wall: float, size: int = 100) -> Entry:
    jpeg = b"\xff\xd8" + b"\x00" * max(0, size - 4) + b"\xff\xd9"
    return Entry(
        t_mono=t_mono,
        t_wall=t_wall,
        jpeg=jpeg,
        status={"fps": 10.0, "face": True, "state": "alert"},
        alert={"pattern": "none", "reasons": [], "t": t_wall},
    )


def test_ring_decimation() -> None:
    ring = FrameRing(seconds=10.0, fps=10.0)
    # interval is 0.1s. If we push with dt < 0.1s, it should drop
    assert ring.push(_make_entry(t_mono=1.0, t_wall=100.0))
    # 0.05s later -> too close, drop
    assert not ring.push(_make_entry(t_mono=1.05, t_wall=100.05))
    assert len(ring) == 1
    # 0.1s later -> accepted
    assert ring.push(_make_entry(t_mono=1.10, t_wall=100.10))
    assert len(ring) == 2


def test_ring_time_eviction() -> None:
    ring = FrameRing(seconds=5.0, fps=10.0)
    base_wall = 1000.0
    for i in range(100):
        t = base_wall + i * 0.1
        ring.push(_make_entry(t_mono=float(i * 0.1), t_wall=t))

    # All entries in ring should be within last 5 seconds of the latest entry
    entries = ring.window(0.0, 2000.0)
    assert len(entries) > 0
    latest_wall = entries[-1].t_wall
    oldest_wall = entries[0].t_wall
    assert latest_wall - oldest_wall <= 5.1


def test_ring_max_bytes_eviction() -> None:
    # 1 entry is roughly ~1000 + 256 = 1256 bytes
    ring = FrameRing(seconds=60.0, fps=10.0, max_bytes=3000)
    assert ring.push(_make_entry(t_mono=1.0, t_wall=10.0, size=1000))
    assert ring.push(_make_entry(t_mono=2.0, t_wall=20.0, size=1000))
    assert len(ring) == 2
    # Pushing third 1000-byte entry will exceed 3000 bytes, evicting the oldest
    assert ring.push(_make_entry(t_mono=3.0, t_wall=30.0, size=1000))
    assert len(ring) <= 2
    assert ring.current_bytes <= 3000
    entries = ring.window(0.0, 100.0)
    assert entries[0].t_wall == 20.0


def test_ring_window() -> None:
    ring = FrameRing(seconds=30.0, fps=10.0)
    for i in range(25):
        ring.push(_make_entry(t_mono=float(i), t_wall=100.0 + i))

    sub = ring.window(105.0, 110.0)
    assert len(sub) == 6
    assert sub[0].t_wall == 105.0
    assert sub[-1].t_wall == 110.0


def test_ring_thread_safety() -> None:
    ring = FrameRing(seconds=10.0, fps=100.0, max_bytes=100_000)
    threads = []

    def _worker(start_idx: int) -> None:
        for i in range(50):
            t = start_idx * 100 + i * 0.02
            ring.push(_make_entry(t_mono=t, t_wall=t))

    for idx in range(4):
        t = threading.Thread(target=_worker, args=(idx,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    assert len(ring) > 0
    assert ring.current_bytes <= 100_000
