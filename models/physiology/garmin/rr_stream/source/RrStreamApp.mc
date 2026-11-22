// START toggles streaming; BACK exits; hold UP/MENU acknowledges an alert.
import Toybox.Application;
import Toybox.Lang;
import Toybox.Sensor;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;
using Toybox.BluetoothLowEnergy as Ble;

class RrStreamApp extends Application.AppBase {
    var link as RrLink;
    var alert as AlertVibe;
    var streaming as Boolean = false;
    var heartRate as Number? = null;
    var motion as Number = 0;
    var rrPerBatch as Number = 0;
    var lastRr as Number? = null;
    var error as String? = null;
    private var _seq as Number = 0;
    private var _echo as Number? = null;
    private var _timer as Timer.Timer? = null;

    function initialize() {
        AppBase.initialize();
        alert = new AlertVibe();
        link = new RrLink(self);
    }

    function onStart(state as Dictionary?) as Void {
        Ble.setDelegate(link);
        link.registerProfile();
        Sensor.setEnabledSensors([Sensor.SENSOR_HEARTRATE]);
        Sensor.enableSensorEvents(method(:onSensorInfo));
        registerSensors();
        _timer = new Timer.Timer();
        (_timer as Timer.Timer).start(method(:onTick), 1000, true);
    }

    private function registerSensors() as Void {
        try {
            Sensor.registerSensorDataListener(method(:onSensorData), {
                :period => 1,
                :heartBeatIntervals => { :enabled => true },
                :accelerometer => { :enabled => true, :sampleRate => 25 }
            });
        } catch (e) {
            // Unsupported acceleration must not disable the existing RR stream.
            try {
                Sensor.registerSensorDataListener(method(:onSensorData), {
                    :period => 1, :heartBeatIntervals => { :enabled => true }
                });
            } catch (fallbackError) {
                error = fallbackError.getErrorMessage();
            }
        }
    }

    function onStop(state as Dictionary?) as Void {
        if (_timer != null) { (_timer as Timer.Timer).stop(); }
        alert.reset();
        link.stop();
        Sensor.unregisterSensorDataListener();
        Sensor.enableSensorEvents(null);
    }

    function toggleStreaming() as Void {
        streaming = !streaming;
        alert.reset();
        _echo = null;
        if (streaming) {
            _seq = 0;
            link.start();
        } else {
            link.stop();
        }
        WatchUi.requestUpdate();
    }

    function onTick() as Void {
        link.tick();
        alert.tick();
        WatchUi.requestUpdate();
    }

    function onSensorInfo(info as Sensor.Info) as Void {
        heartRate = info.heartRate;
    }

    function onAlert(pattern as Number, seq as Number) as Void {
        if (!streaming) { return; }
        _echo = seq;
        // Same-pattern keep-alives still get an echo, but never restart an acknowledged vibe.
        if (alert.change(pattern)) {
            send([] as Array<Number>, false, false, true, System.getTimer());
        }
        WatchUi.requestUpdate();
    }

    function acknowledge() as Void {
        if (!streaming) { return; }
        alert.acknowledge();
        send([] as Array<Number>, false, true, true, System.getTimer());
        WatchUi.requestUpdate();
    }

    private function send(rr as Array<Number>, split as Boolean, ack as Boolean,
                          urgent as Boolean, now as Number) as Void {
        link.enqueue(encodeRrPacket(_seq, now, heartRate, rr, split, motion, ack, _echo), urgent);
        _seq = (_seq + 1) & 0xFFFF;
        _echo = null; // Only the next packet echoes this notification, including an immediate one.
    }

    function onSensorData(data as Sensor.SensorData) as Void {
        motion = motionEnergy(data);
        var rr = [] as Array<Number>;
        var hrData = data.heartRateData;
        if (hrData != null && hrData.heartBeatIntervals != null) {
            rr = hrData.heartBeatIntervals as Array<Number>;
        }
        rrPerBatch = rr.size();
        if (rr.size() > 0) { lastRr = rr[rr.size() - 1]; }
        if (!streaming) { return; }
        if (alert.shake(motion)) { acknowledge(); }
        var now = System.getTimer();
        var start = 0;
        do {
            var end = start + RR_MAX_PER_PACKET;
            if (end > rr.size()) { end = rr.size(); }
            send(rr.slice(start, end), end < rr.size(), false, false, now);
            start = end;
        } while (start < rr.size());
    }

    function getInitialView() as [WatchUi.Views] or [WatchUi.Views, WatchUi.InputDelegates] {
        return [new RrStreamView(self), new RrStreamDelegate(self)];
    }
}

class RrStreamDelegate extends WatchUi.BehaviorDelegate {
    private var _app as RrStreamApp;
    function initialize(app as RrStreamApp) {
        BehaviorDelegate.initialize();
        _app = app;
    }

    function onSelect() as Boolean {
        _app.toggleStreaming();
        return true;
    }

    // FR265/265S: hold middle-left UP (MENU). Lower-right BACK retains normal exit behavior.
    function onMenu() as Boolean {
        _app.acknowledge();
        return true;
    }

    function onBack() as Boolean {
        return false;
    }
}
