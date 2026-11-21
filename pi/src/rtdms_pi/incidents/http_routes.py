"""HTTP routing for incidents API endpoints."""

from __future__ import annotations

import hmac
import json
from collections.abc import Iterator, Mapping
from pathlib import Path

from ..ble.contract import validate
from .sink import IncidentReporter
from .store import IncidentStore


def _stream_range(
    file_path: Path, start: int, length: int, chunk_size: int = 65536
) -> Iterator[bytes]:
    with open(file_path, "rb") as f:
        f.seek(start)
        remaining = length
        while remaining > 0:
            chunk = f.read(min(remaining, chunk_size))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _handle_range(
    file_path: Path, file_size: int, range_header: str
) -> tuple[int, dict[str, str], bytes | Iterator[bytes] | Path]:
    if not range_header.startswith("bytes="):
        return (416, {"Content-Range": f"bytes */{file_size}"}, b"")
    spec = range_header[len("bytes=") :].strip()
    if "-" not in spec:
        return (416, {"Content-Range": f"bytes */{file_size}"}, b"")
    start_str, end_str = spec.split("-", 1)
    try:
        if not start_str:
            suffix_len = int(end_str)
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        elif not end_str:
            start = int(start_str)
            end = file_size - 1
        else:
            start = int(start_str)
            end = int(end_str)
    except ValueError:
        return (416, {"Content-Range": f"bytes */{file_size}"}, b"")

    if start < 0 or start >= file_size or end < start:
        return (416, {"Content-Range": f"bytes */{file_size}"}, b"")
    end = min(end, file_size - 1)
    length = end - start + 1
    stream = _stream_range(file_path, start, length)
    return (
        206,
        {
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(length),
            "Accept-Ranges": "bytes",
        },
        stream,
    )


def _handle_post_incident(
    body: bytes, reporter: IncidentReporter
) -> tuple[int, dict[str, str], bytes | Iterator[bytes] | Path]:
    try:
        req_data = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return (400, {"Content-Type": "application/json"}, b'{"ok":false,"error":"bad json"}')
    clean = validate("incident_request", req_data)
    if clean is None:
        return (
            400,
            {"Content-Type": "application/json"},
            b'{"ok":false,"error":"invalid schema"}',
        )
    try:
        inc_id = reporter.report(clean, clock_offset_ms=None)
        resp = json.dumps({"ok": True, "id": inc_id}, separators=(",", ":")).encode("utf-8")
    except Exception as exc:
        err = (str(exc) or "incident failed")[:64]
        resp = json.dumps({"ok": False, "error": err}, separators=(",", ":")).encode("utf-8")
    return (
        200,
        {"Content-Type": "application/json", "Content-Length": str(len(resp))},
        resp,
    )


def _handle_get_incident_file(
    path: str, headers: Mapping[str, str], store: IncidentStore
) -> tuple[int, dict[str, str], bytes | Iterator[bytes] | Path]:
    parts = path[len("/incidents/") :].split("/")
    if len(parts) != 2:
        return (404, {"Content-Type": "application/json"}, b'{"error":"not found"}')
    inc_id, name = parts
    if ".." in inc_id or "/" in inc_id or "\\" in inc_id:
        return (404, {"Content-Type": "application/json"}, b'{"error":"not found"}')
    if name not in {"clip.mp4", "data.jsonl", "meta.json"}:
        return (404, {"Content-Type": "application/json"}, b'{"error":"not found"}')

    target_path = store.path(inc_id, name)
    if target_path is None or not target_path.is_file():
        return (404, {"Content-Type": "application/json"}, b'{"error":"not found"}')

    size = target_path.stat().st_size
    if name == "clip.mp4":
        range_hdr = next((v for k, v in headers.items() if k.lower() == "range"), None)
        if range_hdr is not None:
            return _handle_range(target_path, size, range_hdr)
        return (
            200,
            {
                "Content-Type": "video/mp4",
                "Content-Length": str(size),
                "Accept-Ranges": "bytes",
            },
            target_path,
        )
    content_type = "application/x-ndjson" if name == "data.jsonl" else "application/json"
    return (
        200,
        {"Content-Type": content_type, "Content-Length": str(size)},
        target_path,
    )


def handle(
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes,
    store: IncidentStore,
    reporter: IncidentReporter,
    token: str,
) -> tuple[int, dict[str, str], bytes | Iterator[bytes] | Path]:
    auth = next((v for k, v in headers.items() if k.lower() == "authorization"), None)
    expected_auth = f"Bearer {token}"
    if auth is None or not hmac.compare_digest(auth, expected_auth):
        return (401, {"Content-Type": "application/json"}, b'{"error":"unauthorized"}')

    if method == "GET" and path == "/incidents":
        payload = json.dumps(store.list_items(), separators=(",", ":")).encode("utf-8")
        return (
            200,
            {"Content-Type": "application/json", "Content-Length": str(len(payload))},
            payload,
        )

    if method == "POST" and path == "/incident":
        return _handle_post_incident(body, reporter)

    if method == "GET" and path.startswith("/incidents/"):
        return _handle_get_incident_file(path, headers, store)

    return (404, {"Content-Type": "application/json"}, b'{"error":"not found"}')
