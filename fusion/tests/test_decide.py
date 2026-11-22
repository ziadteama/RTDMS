from dms_fusion import AlertPattern, decide


def test_phone_sustained_continuous():
    d = decide(phone={"phone_score": 0.9, "sustained_phone_ms": 400})
    assert d.pattern is AlertPattern.CONTINUOUS


def test_face_distracted_beep():
    d = decide(face={"state": "distracted"})
    assert d.pattern is AlertPattern.SHORT_BEEP


def test_physio_does_not_escalate_drowsy():
    d = decide(face={"state": "drowsy"}, physiology={"fatigue_probability": 0.8})
    assert d.pattern is AlertPattern.REPEATED
    assert d.reasons == ["face drowsy"]


def test_physio_alone_never_alerts():
    d = decide(physiology={"fatigue_probability": 0.99, "quality": "good"})
    assert d.pattern is AlertPattern.NONE
    assert d.reasons == []


def test_phone_call_flag_alerts_without_score():
    d = decide(phone={"call": True, "texting": False, "p": 0.4})
    assert d.pattern is AlertPattern.CONTINUOUS
    assert d.reasons == ["phone call"]


def test_phone_texting_flag_alerts():
    d = decide(phone={"call": False, "texting": True})
    assert d.pattern is AlertPattern.CONTINUOUS
    assert d.reasons == ["phone texting"]


def test_phone_flags_false_do_nothing():
    d = decide(phone={"call": False, "texting": False, "p": 0.2})
    assert d.pattern is AlertPattern.NONE


def test_phone_flag_plus_physio_stays_continuous():
    d = decide(phone={"texting": True}, physiology={"fatigue_probability": 0.8})
    assert d.pattern is AlertPattern.CONTINUOUS


def test_eating_and_drinking_never_alert():
    d = decide(phone={"eating": True, "drinking": True, "food_p": 0.95, "call": False})
    assert d.pattern is AlertPattern.NONE
    assert d.reasons == []
