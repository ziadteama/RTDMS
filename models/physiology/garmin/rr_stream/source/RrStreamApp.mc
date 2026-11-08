// RR Stream: reads heart rate and beat-to-beat (RR) intervals from the wrist sensor and, while
// streaming, sends them to the RTDMS Pi over Bluetooth LE.
//
//   START button : start / stop streaming
//   BACK button  : leave the app (streaming stops; the app must stay open to stream)
//
// Every ~1 s the sensor listener hands over the beats since the last call. Those become one
// packet (or two if there were more than 5 beats), stamped with a sequence number and the
// watch's uptime clock, and are queued on the Bluetooth link (RrLink).

import Toybox.Application;
import Toybox.Lang;
import Toybox.Sensor;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;
using Toybox.BluetoothLowEnergy as Ble;

class RrStreamApp extends Application.AppBase {

    var link as RrLink;
    var streaming as Boolean = false;
    var heartRate as Number? = null;  // bpm (null until the sensor locks on)
    var rrPerBatch as Number = 0;     // RR intervals in the last ~1 s batch
    var lastRr as Number? = null;     // most recent RR interval, ms
    var error as String? = null;

    private var _seq as Number = 0;
    private var _timer as Timer.Timer?;

    function initialize() {
        AppBase.initialize();
        link = new RrLink();
    }

    function onStart(state as Dictionary?) as Void {
        Ble.setDelegate(link);
        link.registerProfile();

        Sensor.setEnabledSensors([Sensor.SENSOR_HEARTRATE]);
        Sensor.enableSensorEvents(method(:onSensorInfo));
        try {
            Sensor.registerSensorDataListener(method(:onSensorData), {
                :period => 1,
                :heartBeatIntervals => { :enabled => true }
            });
        } catch (e) {
            error = e.getErrorMessage();
        }

        // Once a second: let the link recover from drops, and refresh the screen.
        _timer = new Timer.Timer();
        (_timer as Timer.Timer).start(method(:onTick), 1000, true);
    }

    function onStop(state as Dictionary?) as Void {
        if (_timer != null) {
            (_timer as Timer.Timer).stop();
        }
        link.stop();
        Sensor.unregisterSensorDataListener();
        Sensor.enableSensorEvents(null);
    }

    // START button.
    function toggleStreaming() as Void {
        streaming = !streaming;
        if (streaming) {
            _seq = 0;  // a new stream starts at 0, so the Pi sees a new session
            link.start();
        } else {
            link.stop();
        }
        WatchUi.requestUpdate();
    }

    function onTick() as Void {
        link.tick();
        WatchUi.requestUpdate();
    }

    function onSensorInfo(info as Sensor.Info) as Void {
        heartRate = info.heartRate;
    }

    function onSensorData(data as Sensor.SensorData) as Void {
        var rr = [] as Array<Number>;
        var hrData = data.heartRateData;
        if (hrData != null && hrData.heartBeatIntervals != null) {
            rr = hrData.heartBeatIntervals as Array<Number>;
        }
        rrPerBatch = rr.size();
        if (rr.size() > 0) {
            lastRr = rr[rr.size() - 1];
        }
        if (!streaming) {
            return;
        }
        // One packet per batch; split into chunks of 5 if needed (SPLIT flag on all but the last).
        var now = System.getTimer();
        var start = 0;
        do {
            var end = start + RR_MAX_PER_PACKET;
            if (end > rr.size()) {
                end = rr.size();
            }
            var chunk = rr.slice(start, end);
            var split = end < rr.size();
            link.enqueue(encodeRrPacket(_seq, now, heartRate, chunk, split));
            _seq = (_seq + 1) & 0xFFFF;
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

    // START / ENTER button.
    function onSelect() as Boolean {
        _app.toggleStreaming();
        return true;
    }
}
