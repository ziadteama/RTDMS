from dms_fusion import AlertPattern, decide


def test_phone_sustained_continuous():
    d = decide(phone={"phone_score": 0.9, "sustained_phone_ms": 400})
    assert d.pattern is AlertPattern.CONTINUOUS


def test_face_distracted_beep():
    d = decide(face={"state": "distracted"})
    assert d.pattern is AlertPattern.SHORT_BEEP


def test_drowsy_plus_physio_max():
    d = decide(face={"state": "drowsy"}, physiology={"fatigue_probability": 0.8})
    assert d.pattern is AlertPattern.MAX
