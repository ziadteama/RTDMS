from __future__ import annotations

import struct
from pathlib import Path

from rtdms_pi.incidents.avi import parse_jpeg_dimensions, write_mjpeg_avi


def _dummy_jpeg(w: int, h: int) -> bytes:
    # Minimal JPEG structure with SOF0 marker containing dimensions
    # 0xFF, 0xC0 (SOF0), length 17, precision 8, height (2 bytes), width (2 bytes), 1 component
    sof0 = struct.pack(">BBHBHHB", 0xFF, 0xC0, 11, 8, h, w, 1) + b"\x01\x11\x00"
    hdr = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    return hdr + sof0 + b"\xff\xd9"


def test_parse_jpeg_dimensions() -> None:
    data = _dummy_jpeg(320, 240)
    w, h = parse_jpeg_dimensions(data)
    assert (w, h) == (320, 240)

    # Fallback on invalid data
    assert parse_jpeg_dimensions(b"not-a-jpeg") == (640, 480)


def test_write_mjpeg_avi(tmp_path: Path) -> None:
    frames = [_dummy_jpeg(160, 120) for _ in range(5)]
    avi_path = tmp_path / "clip.avi"

    count = write_mjpeg_avi(avi_path, frames, fps=10.0)
    assert count == 5
    assert avi_path.is_file()

    content = avi_path.read_bytes()
    # Check RIFF and AVI headers
    assert content[:4] == b"RIFF"
    assert content[8:12] == b"AVI "

    # Check hdrl list
    assert b"LIST" in content
    assert b"hdrl" in content
    assert b"avih" in content

    # Parse avih dwTotalFrames (offset inside avih is 16 bytes: 4 dwords before dwTotalFrames)
    avih_idx = content.find(b"avih")
    assert avih_idx != -1
    avih_size = struct.unpack("<I", content[avih_idx + 4 : avih_idx + 8])[0]
    assert avih_size == 56
    avih_body = content[avih_idx + 8 : avih_idx + 8 + 56]
    total_frames = struct.unpack("<I", avih_body[16:20])[0]
    assert total_frames == 5

    # Check movi list
    assert b"movi" in content

    # Check idx1 chunk
    idx1_idx = content.find(b"idx1")
    assert idx1_idx != -1
    idx1_size = struct.unpack("<I", content[idx1_idx + 4 : idx1_idx + 8])[0]
    assert idx1_size == 5 * 16  # 5 frames * 16 bytes per index entry
