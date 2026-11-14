"""List the file names inside a RAR4 archive (volume) without extracting — read-only header walk.

python rar4_list.py <archive.rar>   -> prints "<unpacked size>\t<name>" per file entry
"""

import struct
import sys

with open(sys.argv[1], "rb") as f:
    assert f.read(7) == b"Rar!\x1a\x07\x00", "not RAR4"
    while True:
        head = f.read(7)
        if len(head) < 7:
            break
        _crc, typ, flags, size = struct.unpack("<HBHH", head)
        add = 0
        body = f.read(size - 7)
        if typ == 0x74:  # file header
            pack, unp, _os, _fcrc, _t, _ver, _meth, nlen, _attr = struct.unpack("<IIBIIBBHI", body[:25])
            off = 25
            if flags & 0x100:
                hp, hu = struct.unpack("<II", body[off:off + 8])
                pack += hp << 32
                unp += hu << 32
                off += 8
            name = body[off:off + nlen].split(b"\x00")[0].decode("utf8", "replace")
            print(f"{unp}\t{name}")
            add = pack
        elif flags & 0x8000:
            add = struct.unpack("<I", body[:4])[0]
        if typ == 0x7B:  # end of archive
            break
        f.seek(add, 1)
