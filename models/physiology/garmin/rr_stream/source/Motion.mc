import Toybox.Lang;
import Toybox.Math;
import Toybox.Sensor;

// Consume each batch in place; retaining acceleration arrays would waste watch memory.
function motionEnergy(data as Sensor.SensorData) as Number {
    var accel = data.accelerometerData;
    if (accel == null) { return 0; }
    var x = accel.x;
    var y = accel.y;
    var z = accel.z;
    if (x == null || y == null || z == null) { return 0; }
    var count = x.size();
    if (y.size() < count) { count = y.size(); }
    if (z.size() < count) { count = z.size(); }
    if (count == 0) { return 0; }
    var total = 0.0;
    for (var i = 0; i < count; i++) {
        // Sensor.AccelerometerData axes are milli-g; float first to avoid integer overflow.
        var ax = x[i].toFloat();
        var ay = y[i].toFloat();
        var az = z[i].toFloat();
        var deviation = Math.sqrt(ax * ax + ay * ay + az * az) - 1000.0;
        total += deviation < 0 ? -deviation : deviation;
    }
    // 1 wire unit = 4 mg mean absolute deviation of magnitude from 1 g; floor and saturate.
    var energy = (total / count / 4.0).toNumber();
    return energy > 255 ? 255 : energy;
}
