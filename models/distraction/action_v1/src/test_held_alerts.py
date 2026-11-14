"""D34: the drinking rule must fire at realistic frame rates (3MDAD 3, SynDD 10, Pi ~20).

python -m pytest models/distraction/action_v1/src/test_held_alerts.py
"""

import pytest
from held_alerts import DrinkingRule

PARAMS = [
    dict(p=0.95, x=5, window=0.3),
    dict(p=0.7, x=10, window=0.5),
    dict(p=0.9, x=5, window=0.3),
]


@pytest.mark.parametrize("fps", [3, 10, 20])
@pytest.mark.parametrize("params", PARAMS)
def test_sustained_cup_fires_once(fps, params):
    rule = DrinkingRule(**params)
    onsets = sum(rule.update(i / fps, True, 0.99, None)[1] for i in range(4 * fps))
    assert onsets == 1


@pytest.mark.parametrize("fps", [3, 10, 20])
@pytest.mark.parametrize("params", PARAMS)
def test_empty_hand_never_fires(fps, params):
    rule = DrinkingRule(**params)
    assert not any(rule.update(i / fps, True, 0.1, None)[1] for i in range(10 * fps))


@pytest.mark.parametrize("fps", [3, 10, 20])
def test_one_frame_blip_does_not_fire(fps):
    rule = DrinkingRule(p=0.9, x=5, window=0.3)
    states = [rule.update(i / fps, i == fps, 0.99, None)[1] for i in range(3 * fps)]
    assert not any(states)


@pytest.mark.parametrize("fps", [3, 10, 20])
def test_sip_uses_nearest_frame_duration_and_two_confirmations(fps):
    rule = DrinkingRule(p=0.95, window=0.3)
    states = [rule.update(i / fps, True, 0.99)[1] for i in range(3 * fps)]
    onset_t = states.index(True) / fps
    expected = 2 / 3 if fps == 3 else 1 / fps + 0.5
    assert onset_t == pytest.approx(expected)


def test_ineligible_sample_resets_sip():
    rule = DrinkingRule(p=0.95, window=0.3)
    assert not rule.update(0, True, 0.99)[1]
    assert not rule.update(1 / 3, True, 0.99)[1]
    assert not rule.update(2 / 3, True, 0.1)[1]
    assert not rule.update(1, True, 0.99)[1]
    assert not rule.update(4 / 3, True, 0.99)[1]
    assert rule.update(5 / 3, True, 0.99)[1]
