from __future__ import annotations

from conftest import Clock
from dms_fusion import AlertPattern

from rtdms_pi.buzzer import PatternPlayer, RecordingBuzzer


def test_pattern_sequences(clock: Clock) -> None:
    backend = RecordingBuzzer()
    player = PatternPlayer(backend, clock=clock, autostart=False)
    player.step()
    assert all(e[0] == "off" for e in backend.events)
    player.set_pattern(AlertPattern.SHORT_BEEP)
    player.step()
    assert backend.events[-1] == ("play", 800, 0.25)
    before = len(backend.events)
    player.set_pattern(AlertPattern.SHORT_BEEP)
    player.step()
    assert len(backend.events) == before
    clock.advance(0.25)
    player.step()
    assert backend.events[-1][0] == "off"
    clock.advance(2.75)
    player.step()
    assert backend.events[-1] == ("play", 800, 0.25)
    player.set_pattern(AlertPattern.REPEATED)
    player.step()
    assert backend.events[-1] == ("play", 800, 0.25)
    clock.advance(0.25)
    player.step()
    assert backend.events[-1][0] == "off"
    clock.advance(0.25)
    player.step()
    assert backend.events[-1][0] == "play"
    player.set_pattern(AlertPattern.CONTINUOUS)
    player.step()
    assert backend.events[-1] == ("play", 1200, float("inf"))
    before = len(backend.events)
    clock.advance(10)
    player.step()
    assert len(backend.events) == before
    player.set_pattern(AlertPattern.MAX)
    player.step()
    assert backend.events[-1] == ("play", 1200, 0.15)
    clock.advance(0.151)
    player.step()
    assert backend.events[-1] == ("play", 1800, 0.15)
    clock.advance(0.15)
    player.step()
    assert backend.events[-1] == ("play", 1200, 0.15)
    player.close()
    assert backend.events[-2:] == [("off", 0, 0), ("close", 0, 0)]


def test_override_restores_latest_live_and_vibration(clock: Clock) -> None:
    class Vibration:
        on_now = False
        closed = False

        def on(self) -> None:
            self.on_now = True

        def off(self) -> None:
            self.on_now = False

        def close(self) -> None:
            self.closed = True

    vibration = Vibration()
    backend = RecordingBuzzer()
    player = PatternPlayer(backend, vibration, clock, autostart=False)
    player.set_pattern(AlertPattern.REPEATED)
    player.step()
    assert vibration.on_now
    player.test_pattern(AlertPattern.MAX, 1)
    player.step()
    assert backend.events[-1][1] == 1200 and vibration.on_now
    player.set_pattern(AlertPattern.SHORT_BEEP)
    clock.advance(1)
    player.step()
    assert backend.events[-1][1] == 800 and not vibration.on_now
    player.set_pattern(AlertPattern.NONE)
    player.step()
    player.set_pattern(AlertPattern.SHORT_BEEP)
    player.step()
    assert backend.events[-1] == ("play", 800, 0.25)
    player.close()
    assert vibration.closed and not vibration.on_now


def test_injected_sleep(clock: Clock) -> None:
    backend = RecordingBuzzer()
    calls = 0
    player = PatternPlayer(backend, clock=clock, autostart=False)

    def sleep(seconds: float) -> None:
        nonlocal calls
        clock.advance(seconds)
        calls += 1
        if calls == 3:
            player._stop.set()

    player._sleep = sleep
    player._thread.start()
    player._thread.join(timeout=1)
    assert not player._thread.is_alive() and calls == 3
    player.close()
