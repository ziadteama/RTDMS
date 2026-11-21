from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from rtdms_pi.settings import SettingsStore
from rtdms_pi.state import RuntimeState


def test_state_clock_offset() -> None:
    state = RuntimeState()
    assert state.clock_offset_ms is None

    state.set_clock_offset(1500)
    assert state.clock_offset_ms == 1500

    state.set_clock_offset(None)
    assert state.clock_offset_ms is None


def test_settings_merged_under_lock() -> None:
    store = SettingsStore()
    updates = [
        {"sensitivity": "high", "detectors": {"phone": False}},
        {"sensitivity": "normal", "detectors": {"distraction": False}},
        {"eye_closure_s": 1.5},
        {"offroad_gaze_s": 1.8},
    ]

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(lambda u: store.update(store.merged(u)), updates * 10))

    read = store.read()
    assert "detectors" in read
    assert isinstance(read["detectors"], dict)
