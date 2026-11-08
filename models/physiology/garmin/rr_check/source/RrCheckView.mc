// The one screen of RR Check: HR, RR intervals per batch, last RR, totals and batch freshness.

import Toybox.Graphics;
import Toybox.Lang;
import Toybox.System;
import Toybox.WatchUi;

class RrCheckView extends WatchUi.View {

    private var _app as RrCheckApp;

    function initialize(app as RrCheckApp) {
        View.initialize();
        _app = app;
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_BLACK);
        dc.clear();
        var w = dc.getWidth();
        var h = dc.getHeight();
        var cx = w / 2;
        var just = Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER;

        if (_app.error != null) {
            dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
            dc.drawText(cx, h / 2, Graphics.FONT_XTINY, "listener error:\n" + _app.error, just);
            return;
        }

        // Heart rate, large.
        var hr = _app.heartRate;
        dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.22, Graphics.FONT_NUMBER_MEDIUM, hr == null ? "--" : hr.toString(),
                    just);
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.36, Graphics.FONT_XTINY, "HR bpm", just);

        // RR intervals in the last ~1 s batch, and the last RR value (ms + the bpm it implies).
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.50, Graphics.FONT_SMALL, "RR/s: " + _app.rrPerBatch.toString(), just);
        var rr = _app.lastRr;
        var rrText = "last RR: --";
        if (rr != null && rr > 0) {
            rrText = "last RR: " + rr.toString() + " ms (" + (60000 / rr).toString() + ")";
        }
        dc.drawText(cx, h * 0.62, Graphics.FONT_SMALL, rrText, just);

        // Totals, and how long ago the last batch came (should stay at 0-1 s).
        var age = _app.batches == 0 ? "-" :
            ((System.getTimer() - _app.lastBatchMs) / 1000).toString() + " s";
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.75, Graphics.FONT_XTINY,
                    "RR total " + _app.totalRr.toString() + "  batches " + _app.batches.toString(),
                    just);
        dc.drawText(cx, h * 0.84, Graphics.FONT_XTINY, "last batch " + age + " ago", just);
    }
}
