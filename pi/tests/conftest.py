from __future__ import annotations

import pytest


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def service(clock: Clock):
    from test_ble_service import fixture

    from rtdms_pi.ble.auth import AuthGate
    from rtdms_pi.ble.fake_gatt import FakeGatt
    from rtdms_pi.ble.phone_service import PhoneService
    from rtdms_pi.buzzer import PatternPlayer, RecordingBuzzer
    from rtdms_pi.incidents_api import MemoryIncidentSink
    from rtdms_pi.settings import SettingsStore
    from rtdms_pi.state import RuntimeState

    player = PatternPlayer(RecordingBuzzer(), clock=clock, autostart=False)
    service = PhoneService(
        FakeGatt(clock),
        RuntimeState(clock=clock),
        player,
        SettingsStore(),
        MemoryIncidentSink(),
        clock,
        AuthGate(fixture("auth")["token"]),
        lambda: fixture("health"),
    )
    yield service
    service.notifier.close()
    player.close()
