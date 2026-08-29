from __future__ import annotations

import asyncio

from dms_physiology.acquisition import ReplaySource
from dms_physiology.fusion import InMemorySink
from dms_physiology.service import STATE_DEGRADED, STATE_VALID, PhysiologyService
from dms_physiology.simulate import synthetic_frames


def test_synthetic_replay_reaches_valid_outputs() -> None:
    sink = InMemorySink()
    asyncio.run(PhysiologyService(ReplaySource(synthetic_frames(70)), sink).run())
    outputs = [
        output for output in sink.outputs if output["state"] in {STATE_VALID, STATE_DEGRADED}
    ]
    assert outputs
    assert outputs[-1]["mean_hr_bpm"] is not None
    assert 55.0 < float(outputs[-1]["mean_hr_bpm"]) < 65.0
