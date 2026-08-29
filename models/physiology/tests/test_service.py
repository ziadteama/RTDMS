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


def test_packet_loss_yield() -> None:
    frames = synthetic_frames(200)
    
    # 0%, 2.5% (1 in 40), 5% (1 in 20), 10% (1 in 10)
    strategies = [
        (0.0, lambda i: False),
        (0.025, lambda i: (i % 40) == 39),
        (0.05, lambda i: (i % 20) == 19),
        (0.10, lambda i: (i % 10) == 9),
    ]

    print()
    print(f"{'loss pattern':<28} {'outputs':>7} {'with HR':>9} {'HR yield':>10}")
    
    for loss_rate, drop_fn in strategies:
        sink = InMemorySink()
        kept_frames = [f for i, f in enumerate(frames) if not drop_fn(i)]
        
        asyncio.run(PhysiologyService(ReplaySource(kept_frames), sink).run())
        
        total_outputs = len(sink.outputs)
        with_hr = sum(1 for o in sink.outputs if o["mean_hr_bpm"] is not None)
        hr_yield = with_hr / max(1, total_outputs)
        
        pattern = (
            "none"
            if loss_rate == 0
            else f"gap every {int(1 / loss_rate)} pkts ({loss_rate * 100:g}%)"
        )
        print(f"{pattern:<28} {total_outputs:>7} {with_hr:>9} {hr_yield*100:>9.0f}%")
        
        if loss_rate <= 0.05:
            assert hr_yield >= 0.50, f"HR yield {hr_yield} fell below 50% at {loss_rate} loss"

