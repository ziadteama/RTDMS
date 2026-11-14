"""D31: the drinking rule must fire at any realistic frame rate (3MDAD is 3 fps, SynDD 10, Pi ~20).

python -m pytest models/distraction/action_v1/src/test_held_alerts.py
"""

import pytest
from held_alerts import DrinkingRule

PARAMS = [dict(p=0.95, x=5, window=0.3), dict(p=0.7, x=10, window=0.5), dict(p=0.9, x=5, window=0.3)]


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
