// The Bluetooth side of RR Stream: find the RTDMS Pi, connect, and write packets to it.
//
// States:  idle -> scanning -> connecting -> finding service -> connected
//                      ^                                          |
//                      +-------------- reconnecting <-------------+  (link lost)
//
// - Scanning looks for the 16-bit RR service UUID 0xFFF0 in advertisements. Garmin watches only
//   report devices that advertise a 16-bit service UUID in General Discoverable mode, so the
//   service is 16-bit (docs/packet_format.md). 0xFFF0 is a common vendor-test value, so a device
//   is only kept if its FFF0 service has our unique 128-bit RR characteristic.
// - After pairing, Garmin's Bluetooth system reconnects to the same Pi by itself when the link
//   drops; if that has not happened within RECONNECT_MS, we unpair and scan again.
// - Packets wait in a small queue and are written one at a time (write with response, so we
//   know each one arrived before sending the next). When the queue is full the oldest packet is
//   dropped; the Pi sees the missing sequence numbers and counts them as lost.

import Toybox.Lang;
import Toybox.System;
using Toybox.BluetoothLowEnergy as Ble;

const RR_SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb";
const RR_CHARACTERISTIC_UUID = "1375193a-7edb-4a34-b3f2-18130239c8a8";
const RECONNECT_MS = 10000;      // give the system this long to reconnect by itself
const CONNECT_MS = 15000;        // give a fresh connection attempt this long
const SERVICE_LOOKUP_MS = 8000;  // after connecting, keep looking for the RR characteristic
const QUEUE_MAX = 60;            // ~1 minute of packets while the Pi is away

class RrLink extends Ble.BleDelegate {

    var state as String = "idle";
    var sent as Number = 0;          // packets the Pi acknowledged
    var dropped as Number = 0;       // packets thrown away because the queue was full
    var writeErrors as Number = 0;
    var profileOk as Boolean = false;
    // Diagnostics shown on screen until the link is up.
    var scanSeen as Number = 0;      // scan results received
    var connects as Number = 0;      // links that reached CONNECTED
    var noService as Number = 0;     // links dropped because the RR characteristic was missing
    var serviceFound as Boolean = false;  // last lookup: FFF0 service present

    private var _service as Ble.Uuid;
    private var _char as Ble.Uuid;
    private var _wanted as Boolean = false;          // the user pressed START
    private var _device as Ble.Device? = null;
    private var _characteristic as Ble.Characteristic? = null;
    private var _queue as Array<ByteArray> = [] as Array<ByteArray>;
    private var _busy as Boolean = false;            // a write is in flight
    private var _since as Number = 0;                // System.getTimer() when the state began

    function initialize() {
        BleDelegate.initialize();
        _service = Ble.stringToUuid(RR_SERVICE_UUID);
        _char = Ble.stringToUuid(RR_CHARACTERISTIC_UUID);
    }

    // Tell the BLE system which service / characteristic we will use (once, at app start).
    // Same form as Garmin's NordicThingy52CoinCollector sample for a write-only characteristic.
    function registerProfile() as Void {
        Ble.registerProfile({
            :uuid => _service,
            :characteristics => [{ :uuid => _char }]
        });
    }

    function queueSize() as Number {
        return _queue.size();
    }

    // START pressed.
    function start() as Void {
        _wanted = true;
        _queue = [] as Array<ByteArray>;
        scan();
    }

    // STOP pressed, or the app is closing.
    function stop() as Void {
        _wanted = false;
        Ble.setScanState(Ble.SCAN_STATE_OFF);
        forgetDevice();
        _queue = [] as Array<ByteArray>;
        setState("idle");
    }

    // Called once a second by the app: finish the service lookup, and recover from a link that
    // does not come back by itself.
    function tick() as Void {
        if (!_wanted) {
            return;
        }
        var age = System.getTimer() - _since;
        if (state.equals("finding service")) {
            if (!findCharacteristic() && age > SERVICE_LOOKUP_MS) {
                // Connected, but no RR characteristic: another device with an FFF0 service, or
                // the Pi receiver is not running. Drop it and look on.
                noService += 1;
                forgetDevice();
                scan();
            }
            return;
        }
        if ((state.equals("reconnecting") && age > RECONNECT_MS) ||
            (state.equals("connecting") && age > CONNECT_MS)) {
            forgetDevice();
            scan();
        }
    }

    // New packet from the sensor callback.
    function enqueue(packet as ByteArray) as Void {
        if (!_wanted) {
            return;
        }
        if (_queue.size() >= QUEUE_MAX) {
            _queue = _queue.slice(1, null);
            dropped += 1;
        }
        _queue.add(packet);
        pump();
    }

    // ---------------------------------------------------------------- BleDelegate callbacks

    function onProfileRegister(uuid as Ble.Uuid, status as Ble.Status) as Void {
        profileOk = (status == Ble.STATUS_SUCCESS);
    }

    function onScanResults(scanResults as Ble.Iterator) as Void {
        if (!state.equals("scanning")) {
            return;
        }
        for (var r = scanResults.next(); r != null; r = scanResults.next()) {
            if (!(r instanceof Ble.ScanResult)) {
                continue;
            }
            scanSeen += 1;
            if (advertises(r.getServiceUuids(), _service)) {
                Ble.setScanState(Ble.SCAN_STATE_OFF);
                setState("connecting");
                _device = Ble.pairDevice(r);
                if (_device == null) {
                    scan();  // pairing refused right away: keep looking
                }
                return;
            }
        }
    }

    function onConnectedStateChanged(device as Ble.Device, connState as Ble.ConnectionState) as Void {
        _busy = false;
        if (connState == Ble.CONNECTION_STATE_CONNECTED) {
            _device = device;
            connects += 1;
            setState("finding service");  // tick() keeps looking for SERVICE_LOOKUP_MS
            findCharacteristic();
        } else {
            _characteristic = null;
            if (_wanted) {
                setState("reconnecting");
            }
        }
    }

    function onCharacteristicWrite(characteristic as Ble.Characteristic, status as Ble.Status) as Void {
        _busy = false;
        if (_queue.size() > 0) {
            _queue = _queue.slice(1, null);  // done with it: delivered, or failed and skipped
        }
        if (status == Ble.STATUS_SUCCESS) {
            sent += 1;
        } else {
            writeErrors += 1;
        }
        pump();
    }

    // ---------------------------------------------------------------- helpers

    // Write the oldest queued packet, if the link is up and nothing is in flight.
    private function pump() as Void {
        if (_busy || _characteristic == null || _queue.size() == 0) {
            return;
        }
        _busy = true;
        try {
            (_characteristic as Ble.Characteristic).requestWrite(_queue[0],
                {:writeType => Ble.WRITE_TYPE_WITH_RESPONSE});
        } catch (e) {
            _busy = false;
            writeErrors += 1;
            _queue = _queue.slice(1, null);
        }
    }

    // Look up the RR characteristic on the connected device; true once it is found.
    private function findCharacteristic() as Boolean {
        if (_device == null) {
            return false;
        }
        var service = (_device as Ble.Device).getService(_service);
        serviceFound = (service != null);
        _characteristic = (service != null) ? service.getCharacteristic(_char) : null;
        if (_characteristic == null) {
            return false;
        }
        setState("connected");
        pump();
        return true;
    }

    private function scan() as Void {
        setState("scanning");
        Ble.setScanState(Ble.SCAN_STATE_SCANNING);
    }

    private function forgetDevice() as Void {
        _characteristic = null;
        _busy = false;
        if (_device != null) {
            Ble.unpairDevice(_device as Ble.Device);
            _device = null;
        }
    }

    private function setState(s as String) as Void {
        state = s;
        _since = System.getTimer();
    }

    private function advertises(uuids as Ble.Iterator, wanted as Ble.Uuid) as Boolean {
        for (var u = uuids.next(); u != null; u = uuids.next()) {
            if (u.equals(wanted)) {
                return true;
            }
        }
        return false;
    }
}
