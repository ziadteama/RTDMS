// Builds one RR packet exactly as docs/packet_format.md describes (version 1, little-endian):
//
//   [0] version  [1] flags  [2-3] seq  [4-7] watch_ms  [8] hr  [9] rr_count  [10..] rr_ms x n
//
// At most 5 RR intervals per packet, so a packet is never longer than 20 bytes (the Connect IQ
// limit for one Bluetooth write).

import Toybox.Lang;

const RR_PACKET_VERSION = 1;
const RR_FLAG_HR_VALID = 1;
const RR_FLAG_SPLIT = 2;
const RR_MAX_PER_PACKET = 5;

function encodeRrPacket(seq as Number, watchMs as Number, hr as Number?, rr as Array<Number>,
                        split as Boolean) as ByteArray {
    var n = rr.size();
    var bytes = new [10 + 2 * n]b;
    var flags = 0;
    var hrByte = 0;  // 0 + no HR_VALID flag when the watch has no heart rate yet
    if (hr != null && hr > 0 && hr < 256) {
        flags |= RR_FLAG_HR_VALID;
        hrByte = hr;
    }
    if (split) {
        flags |= RR_FLAG_SPLIT;
    }
    bytes[0] = RR_PACKET_VERSION;
    bytes[1] = flags;
    bytes.encodeNumber(seq & 0xFFFF, Lang.NUMBER_FORMAT_UINT16, {:offset => 2, :endianness => Lang.ENDIAN_LITTLE});
    // System.getTimer() is a signed 32-bit number; its bit pattern is the uint32 the Pi expects.
    bytes.encodeNumber(watchMs, Lang.NUMBER_FORMAT_SINT32, {:offset => 4, :endianness => Lang.ENDIAN_LITTLE});
    bytes[8] = hrByte;
    bytes[9] = n;
    for (var i = 0; i < n; i++) {
        var value = rr[i];
        if (value < 0) { value = 0; }
        if (value > 65535) { value = 65535; }
        bytes.encodeNumber(value, Lang.NUMBER_FORMAT_UINT16, {:offset => 10 + 2 * i, :endianness => Lang.ENDIAN_LITTLE});
    }
    return bytes;
}
