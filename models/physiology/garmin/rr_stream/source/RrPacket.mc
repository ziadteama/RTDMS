// V2 fits four RR intervals in the Connect IQ 20-byte write limit.
import Toybox.Lang;

const RR_PACKET_VERSION = 2;
const RR_FLAG_HR_VALID = 1;
const RR_FLAG_SPLIT = 2;
const RR_FLAG_ACK = 4;
const RR_FLAG_ECHO_VALID = 8;
const RR_FLAG_CONTACT = 16;
const RR_MAX_PER_PACKET = 4;

function encodeRrPacket(seq as Number, watchMs as Number, hr as Number?,
                        rr as Array<Number>, split as Boolean, motion as Number,
                        ack as Boolean, echo as Number?) as ByteArray {
    var n = rr.size();
    if (n > RR_MAX_PER_PACKET) { n = RR_MAX_PER_PACKET; }
    var bytes = new [12 + 2 * n]b;
    var flags = 0;
    var hrByte = 0;
    if (hr != null && hr > 0 && hr < 256) {
        flags |= RR_FLAG_HR_VALID;
        hrByte = hr;
    }
    // Sensor.Info has no skin-contact flag: any non-null HR is our approximation.
    if (hr != null) { flags |= RR_FLAG_CONTACT; }
    if (split) { flags |= RR_FLAG_SPLIT; }
    if (ack) { flags |= RR_FLAG_ACK; }
    if (echo != null) { flags |= RR_FLAG_ECHO_VALID; }
    bytes[0] = RR_PACKET_VERSION;
    bytes[1] = flags;
    bytes.encodeNumber(seq & 0xFFFF, Lang.NUMBER_FORMAT_UINT16,
        {:offset => 2, :endianness => Lang.ENDIAN_LITTLE});
    // Signed encoding preserves System.getTimer()'s uint32 bit pattern, including wrap.
    bytes.encodeNumber(watchMs, Lang.NUMBER_FORMAT_SINT32,
        {:offset => 4, :endianness => Lang.ENDIAN_LITTLE});
    bytes[8] = hrByte;
    bytes[9] = motion < 0 ? 0 : (motion > 255 ? 255 : motion);
    bytes[10] = echo == null ? 0 : (echo & 0xFF);
    bytes[11] = n;
    for (var i = 0; i < n; i++) {
        var value = rr[i];
        if (value < 0) { value = 0; }
        if (value > 65535) { value = 65535; }
        bytes.encodeNumber(value, Lang.NUMBER_FORMAT_UINT16,
            {:offset => 12 + 2 * i, :endianness => Lang.ENDIAN_LITTLE});
    }
    return bytes;
}
