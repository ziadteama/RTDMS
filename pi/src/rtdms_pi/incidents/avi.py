"""Minimal MJPEG AVI container muxer."""

from __future__ import annotations

import struct
from pathlib import Path


def parse_jpeg_dimensions(data: bytes) -> tuple[int, int]:
    """Extract width and height from JPEG header bytes, or default to (640, 480)."""
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return (640, 480)
    idx = 2
    while idx < len(data) - 8:
        if data[idx] != 0xFF:
            idx += 1
            continue
        marker = data[idx + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", data[idx + 5 : idx + 9])
            return (w, h)
        if marker in (0xD9, 0xDA):
            break
        length = struct.unpack(">H", data[idx + 2 : idx + 4])[0]
        idx += 2 + length
    return (640, 480)


def _build_strl(
    fps: float, frame_count: int, max_frame_size: int, width: int, height: int
) -> bytes:
    rate = int(round(fps * 1000))
    scale = 1000
    strh = struct.pack(
        "<4s4sIHHIIIIIIIIhhhh",
        b"vids",
        b"MJPG",
        0,
        0, 0,
        0,
        scale,
        rate,
        0,
        frame_count,
        max_frame_size,
        0xFFFFFFFF,
        0,
        0, 0, width, height,
    )
    strf = struct.pack(
        "<IiiHH4sIiiII",
        40,
        width,
        height,
        1,
        24,
        b"MJPG",
        width * height * 3,
        0, 0, 0, 0,
    )
    strl_data = (
        b"strh"
        + struct.pack("<I", len(strh))
        + strh
        + b"strf"
        + struct.pack("<I", len(strf))
        + strf
    )
    return b"LIST" + struct.pack("<I", len(strl_data) + 4) + b"strl" + strl_data


def _build_avi_headers(
    frame_count: int,
    max_frame_size: int,
    fps: float,
    width: int,
    height: int,
) -> bytes:
    us_per_frame = int(1_000_000 / fps)
    avih = struct.pack(
        "<14I",
        us_per_frame,
        int(max_frame_size * fps),
        0,
        0x10,  # AVIF_HASINDEX
        frame_count,
        0,
        1,
        max_frame_size,
        width,
        height,
        0, 0, 0, 0,
    )
    strl_list = _build_strl(fps, frame_count, max_frame_size, width, height)
    hdrl_data = b"avih" + struct.pack("<I", len(avih)) + avih + strl_list
    return b"LIST" + struct.pack("<I", len(hdrl_data) + 4) + b"hdrl" + hdrl_data


def write_mjpeg_avi(
    output_path: Path | str,
    frames: list[bytes],
    fps: float = 10.0,
    width: int | None = None,
    height: int | None = None,
) -> int:
    """Write MJPEG frames to an AVI file with an idx1 index."""
    fps = max(float(fps), 1.0)
    frame_count = len(frames)
    max_frame_size = max((len(f) for f in frames), default=0)

    if (width is None or height is None) and frames:
        w_parsed, h_parsed = parse_jpeg_dimensions(frames[0])
        width = width if width is not None else w_parsed
        height = height if height is not None else h_parsed
    w = width or 640
    h = height or 480

    hdrl_list = _build_avi_headers(frame_count, max_frame_size, fps, w, h)

    movi_chunks = bytearray()
    idx1_entries = bytearray()
    current_offset = 4

    for frame in frames:
        chunk_len = len(frame)
        pad = b"\x00" if (chunk_len % 2 != 0) else b""
        movi_chunks.extend(b"00dc" + struct.pack("<I", chunk_len) + frame + pad)
        idx1_entries.extend(struct.pack("<4sIII", b"00dc", 0x10, current_offset, chunk_len))
        current_offset += 8 + chunk_len + len(pad)

    movi_list = b"LIST" + struct.pack("<I", len(movi_chunks) + 4) + b"movi" + movi_chunks
    idx1_chunk = b"idx1" + struct.pack("<I", len(idx1_entries)) + idx1_entries

    riff_data = b"AVI " + hdrl_list + movi_list + idx1_chunk
    riff_file = b"RIFF" + struct.pack("<I", len(riff_data)) + riff_data

    Path(output_path).write_bytes(riff_file)
    return frame_count
