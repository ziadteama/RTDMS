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
        var cx = dc.getWidth() / 2;
        var h = dc.getHeight();
        var just = Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER;
        var hr = _app.heartRate;
        dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.18, Graphics.FONT_NUMBER_MEDIUM,
                    hr == null ? "--" : hr.toString(), just);
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.30, Graphics.FONT_XTINY, "HR bpm", just);
        drawAlert(dc, cx, h, just);
        drawDiagnostics(dc, cx, h, just);
    }

    private function drawAlert(dc as Graphics.Dc, cx as Number, h as Number,
                               just as Number) as Void {
        var title = _app.streaming ? _app.link.state.toUpper() : "PRESS START";
        dc.setColor(Graphics.COLOR_GREEN, Graphics.COLOR_TRANSPARENT);
        if (_app.alert.pattern != 0) {
            title = _app.alert.pattern == 4 ? "Driver not responding" : "Alert";
            if (_app.alert.acknowledged) { title = "Acknowledged"; }
            dc.setColor(Graphics.COLOR_YELLOW, Graphics.COLOR_TRANSPARENT);
        }
        // XTINY keeps the longest alert readable on the smaller 265S round display.
        dc.drawText(cx, h * 0.41, Graphics.FONT_XTINY, title, just);
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.51, Graphics.FONT_XTINY, "Hold UP: I'm OK", just);
    }

    private function drawDiagnostics(dc as Graphics.Dc, cx as Number, h as Number,
                                     just as Number) as Void {
        var link = _app.link;
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.61, Graphics.FONT_XTINY,
            "sent " + link.sent + " q " + link.queueSize() + " RR/s " + _app.rrPerBatch, just);
        dc.drawText(cx, h * 0.70, Graphics.FONT_XTINY,
            "motion " + _app.motion + " drop " + link.dropped + " err " + link.writeErrors, just);
        var diagnostic = link.subscribed ? "Alerts connected" : "Alerts unavailable";
        if (!link.profileOk) { diagnostic = "BLE profile pending"; }
        if (link.state.equals("scanning")) { diagnostic = "Scan seen " + link.scanSeen; }
        if (_app.error != null) { diagnostic = "Sensor error"; }
        dc.drawText(cx, h * 0.79, Graphics.FONT_XTINY, diagnostic, just);
        dc.drawText(cx, h * 0.87, Graphics.FONT_XTINY, "BACK: exit", just);
    }
}
