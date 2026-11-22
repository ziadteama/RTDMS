import Toybox.Attention;
import Toybox.Lang;
import Toybox.System;

class AlertVibe {
    var pattern as Number = 0;
    var acknowledged as Boolean = false;
    private var _lastPulse as Number = 0;
    private var _shakes as Number = 0;

    function initialize() {}

    function change(next as Number) as Boolean {
        if (next == pattern) { return false; }
        stopPulse();
        pattern = next;
        acknowledged = false;
        _shakes = 0;
        pulse();
        return true;
    }

    function active() as Boolean {
        return pattern != 0 && !acknowledged;
    }

    function acknowledge() as Void {
        acknowledged = true;
        _shakes = 0;
        stopPulse();
    }

    function reset() as Void {
        pattern = 0;
        acknowledged = false;
        _shakes = 0;
        stopPulse();
    }

    function shake(motion as Number) as Boolean {
        if (!active() || motion < 200) {
            _shakes = 0;
            return false;
        }
        _shakes += 1;
        return _shakes >= 2;
    }

    function tick() as Void {
        if (!active() || pattern < 3) { return; }
        var interval = pattern == 4 ? 1000 : 2000;
        if (System.getTimer() - _lastPulse >= interval) { pulse(); }
    }

    private function stopPulse() as Void {
        if (Attention has :vibrate) {
            // Replace an outstanding pattern with a silent pulse, including on ACK/exit.
            Attention.vibrate([new Attention.VibeProfile(0, 1)]);
        }
    }

    private function pulse() as Void {
        _lastPulse = System.getTimer();
        if (!(Attention has :vibrate) || !active()) { return; }
        if (pattern == 1) {
            Attention.vibrate([new Attention.VibeProfile(70, 200)]);
        } else if (pattern == 2) {
            Attention.vibrate([new Attention.VibeProfile(70, 300),
                new Attention.VibeProfile(0, 200), new Attention.VibeProfile(70, 300),
                new Attention.VibeProfile(0, 200), new Attention.VibeProfile(70, 300)]);
        } else {
            Attention.vibrate([new Attention.VibeProfile(pattern == 4 ? 100 : 70, 1000)]);
        }
    }
}
