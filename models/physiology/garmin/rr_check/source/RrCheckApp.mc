// RR Check: shows whether the watch delivers beat-to-beat (RR) intervals to a Connect IQ app.
//
// Two data paths, both from the wrist optical sensor:
//   1. Sensor.enableSensorEvents      -> Sensor.Info.heartRate  (the HR the watch shows)
//   2. Sensor.registerSensorDataListener with :heartBeatIntervals -> a batch of RR intervals (ms)
//      roughly once per second (:period => 1).
// The screen shows HR, how many RR intervals arrived in the last batch ("RR/s"), and the last RR
// value, so it can be checked against a pulse taken by hand (60000 / RR = beats per minute).

import Toybox.Application;
import Toybox.Lang;
import Toybox.Sensor;
import Toybox.System;
import Toybox.WatchUi;

class RrCheckApp extends Application.AppBase {

    var heartRate as Number? = null;     // bpm from Sensor.Info (null until the sensor locks on)
    var rrPerBatch as Number = 0;        // RR intervals in the most recent ~1 s batch
    var lastRr as Number? = null;        // most recent RR interval, ms
    var totalRr as Number = 0;           // RR intervals since the app started
    var batches as Number = 0;           // listener callbacks since the app started
    var lastBatchMs as Number = 0;       // System.getTimer() at the last callback
    var error as String? = null;         // shown on screen if the listener could not start

    function initialize() {
        AppBase.initialize();
    }

    function onStart(state as Dictionary?) as Void {
        // Path 1: plain heart rate, delivered about once per second.
        Sensor.setEnabledSensors([Sensor.SENSOR_HEARTRATE]);
        Sensor.enableSensorEvents(method(:onSensorInfo));

        // Path 2: beat-to-beat intervals. Only one sensor data listener may be active.
        try {
            Sensor.registerSensorDataListener(method(:onSensorData), {
                :period => 1,
                :heartBeatIntervals => { :enabled => true }
            });
        } catch (e) {
            error = e.getErrorMessage();
        }
    }

    function onStop(state as Dictionary?) as Void {
        Sensor.unregisterSensorDataListener();
        Sensor.enableSensorEvents(null);
    }

    function onSensorInfo(info as Sensor.Info) as Void {
        heartRate = info.heartRate;
        WatchUi.requestUpdate();
    }

    function onSensorData(data as Sensor.SensorData) as Void {
        batches += 1;
        lastBatchMs = System.getTimer();
        rrPerBatch = 0;
        var hrData = data.heartRateData;
        if (hrData != null) {
            var intervals = hrData.heartBeatIntervals;
            if (intervals != null && intervals.size() > 0) {
                rrPerBatch = intervals.size();
                totalRr += rrPerBatch;
                lastRr = intervals[intervals.size() - 1];
            }
        }
        WatchUi.requestUpdate();
    }

    function getInitialView() as [WatchUi.Views] or [WatchUi.Views, WatchUi.InputDelegates] {
        return [new RrCheckView(self)];
    }
}
