from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from link_spike.proc_sample import (  # noqa: E402
    Sample,
    compute_deltas,
    parse_stat,
    parse_status,
    sample_process,
    summarize,
)


def test_parse_stat_with_parentheses_and_spaces() -> None:
    text = "42 (worker (a) b)) S 1 2 3 4 5 6 7 8 9 10 120 30 999 888 20 0 7 0 456 0 0"
    stat = parse_stat(text)
    assert stat.cpu_ticks == 150  # Does not include child utime/stime.
    assert stat.threads == 7
    assert stat.start_ticks == 456
    with pytest.raises(ValueError):
        parse_stat("42 (truncated) S 1")


def test_parse_status() -> None:
    text = """Name:\tworker
VmSize:\t99999 kB
VmRSS:\t2048 kB
Threads:\t7
voluntary_ctxt_switches:\t120
nonvoluntary_ctxt_switches:\t30
"""
    assert parse_status(text) == {
        "VmRSS": 2048, "voluntary_ctxt_switches": 120, "nonvoluntary_ctxt_switches": 30,
    }
    with pytest.raises(ValueError):
        parse_status("Name:\texited\n")


def test_deltas_and_weighted_summary() -> None:
    a = Sample(10, 2, 2048, 10, 20, 3, 100)
    b = Sample(11, 4, 3072, 14, 22, 5, 100)
    c = Sample(14, 5, 1024, 18, 24, 4, 100)
    assert compute_deltas(a, b) == {
        "seconds": 1, "cpu_pct": 200, "voluntary_per_s": 4, "nonvoluntary_per_s": 2,
    }
    summary = summarize([a, b, c])
    assert summary["cpu_avg_pct"] == 75
    assert summary["cpu_max_pct"] == 200
    assert summary["rss_start_mb"] == 2
    assert summary["rss_end_mb"] == 1
    assert summary["rss_delta_mb"] == -1
    assert summary["voluntary_per_s"] == 2
    assert summary["nonvoluntary_per_s"] == 1
    assert summary["threads_max"] == 5
    for invalid in (a, replace(b, start_ticks=101), replace(b, cpu_s=1)):
        with pytest.raises(ValueError):
            compute_deltas(a, invalid)


def test_load_is_reaped_on_sampling_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from link_spike import proc_sample

    children = []

    class Child:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.killed = False
            self.waited = False
            children.append(self)

        def poll(self) -> None:
            return None

        def kill(self) -> None:
            self.killed = True

        def wait(self) -> int:
            self.waited = True
            return -9

    def fail(*args: object) -> Sample:
        raise ProcessLookupError

    monkeypatch.setattr("link_spike.proc_sample.subprocess.Popen", Child)
    monkeypatch.setattr(proc_sample, "read_sample", fail)
    with pytest.raises(ProcessLookupError):
        sample_process(42, 1, 1, 2)
    assert len(children) == 2
    assert all(child.killed and child.waited for child in children)
