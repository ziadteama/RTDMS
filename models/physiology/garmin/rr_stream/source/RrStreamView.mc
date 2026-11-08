// The one screen of RR Stream: heart rate, link state, packets sent, last RR.

import Toybox.Graphics;
import Toybox.Lang;
import Toybox.WatchUi;

class RrStreamView extends WatchUi.View {

    private var _app as RrStreamApp;

    function initialize(app as RrStreamApp) {
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
        var link = _app.link;

        if (_app.error != null) {
            dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
            dc.drawText(cx, h / 2, Graphics.FONT_XTINY, "sensor error:\n" + _app.error, just);
            return;
        }

        // Heart rate.
        var hr = _app.heartRate;
        dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.20, Graphics.FONT_NUMBER_MEDIUM, hr == null ? "--" : hr.toString(),
                    just);
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.33, Graphics.FONT_XTINY, "HR bpm", just);

        // Link state: green when connected, yellow while looking, grey when idle.
        var colour = Graphics.COLOR_LT_GRAY;
        if (link.state.equals("connected")) {
            colour = Graphics.COLOR_GREEN;
        } else if (!link.state.equals("idle")) {
            colour = Graphics.COLOR_YELLOW;
        }
        dc.setColor(colour, Graphics.COLOR_TRANSPARENT);
        var title = _app.streaming ? link.state.toUpper() : "PRESS START";
        dc.drawText(cx, h * 0.46, Graphics.FONT_SMALL, title, just);

        // Counters.
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.58, Graphics.FONT_XTINY,
                    "sent " + link.sent.toString() + "  queue " + link.queueSize().toString(), just);
        var rr = _app.lastRr;
        dc.drawText(cx, h * 0.68, Graphics.FONT_XTINY,
                    "RR/s " + _app.rrPerBatch.toString() + "  last RR " +
                    ((rr == null) ? "--" : rr.toString() + " ms"), just);
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.78, Graphics.FONT_XTINY,
                    "dropped " + link.dropped.toString() + "  errors " + link.writeErrors.toString(),
                    just);
        if (!link.profileOk) {
            dc.drawText(cx, h * 0.87, Graphics.FONT_XTINY, "BLE profile not registered", just);
        } else if (link.connects > 0 && !link.state.equals("connected")) {
            // Link diagnostics: connections, drops for a missing RR service, service seen.
            dc.drawText(cx, h * 0.87, Graphics.FONT_XTINY,
                        "conn " + link.connects.toString() + " nosvc " + link.noService.toString() +
                        " svc " + (link.serviceFound ? "yes" : "no"), just);
        } else if (link.state.equals("scanning")) {
            // How many advertisements the scan has seen so far.
            dc.drawText(cx, h * 0.87, Graphics.FONT_XTINY,
                        "seen " + link.scanSeen.toString(), just);
        }
    }
}
