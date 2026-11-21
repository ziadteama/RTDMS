"""Minimal HTTP debug surface; deployment authentication belongs to the link layer."""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dms_fusion import AlertPattern

from .buzzer import PatternPlayer
from .config import RuntimeConfig
from .payloads import (
    alert_payload,
    health_payload,
    physio_payload,
    status_payload,
    to_json_bytes,
)
from .state import RuntimeState


class DebugServer:
    def __init__(self, state: RuntimeState, player: PatternPlayer, config: RuntimeConfig) -> None:
        started, cpu_started = time.monotonic(), time.process_time()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass  # never log request bodies / biometric values

            def reply(self, code: int, payload: dict[str, object]) -> None:
                data = to_json_bytes(payload)
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                s = state.snapshot()
                if self.path == "/alert":
                    payload = alert_payload(s.decision, time.time())
                elif self.path == "/status":
                    payload = status_payload(s)
                elif self.path == "/physio":
                    payload = physio_payload(s)
                elif self.path == "/health":
                    elapsed = time.monotonic() - started
                    payload = health_payload(
                        cpu_pct=100 * (time.process_time() - cpu_started) / max(elapsed, 1e-9),
                        fps=s.fps,
                        uptime_s=elapsed,
                        camera=s.camera_ok,
                        temp_c=s.temp_c,
                        models={
                            "fusion": "running",
                            "face": "running"
                            if s.face and s.camera_ok
                            else "off"
                            if config.no_camera
                            else "error",
                            "distraction": "off"
                            if config.no_camera
                            else "running"
                            if s.camera_ok
                            else "error",
                            "physiology": "running"
                            if s.physio
                            else "error"
                            if config.physiology
                            else "off",
                        },
                    )
                else:
                    self.reply(404, {"error": "not found"})
                    return
                self.reply(200, payload)

            def do_POST(self) -> None:
                if self.path != "/test_alert":
                    self.reply(404, {"error": "not found"})
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 1024:
                        raise ValueError("invalid body length")
                    body = json.loads(self.rfile.read(size))
                    if not isinstance(body, dict) or not isinstance(body.get("pattern"), str):
                        raise ValueError("pattern required")
                    pattern = AlertPattern(body["pattern"])
                except (ValueError, UnicodeError):
                    self.reply(400, {"error": "invalid pattern or body"})
                    return
                player.test_pattern(pattern, 2.0)
                self.reply(200, {"ok": True})

            def setup(self) -> None:
                self.request.settimeout(2)
                super().setup()

        class Server(ThreadingHTTPServer):
            address_family = socket.AF_INET6 if ":" in config.host else socket.AF_INET
            daemon_threads = True

        self.server = Server((config.host, config.http_port), Handler)
        self._thread = threading.Thread(
            target=self.server.serve_forever, daemon=True, name="http-debug"
        )

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        if self._thread.is_alive():
            self.server.shutdown()
            self._thread.join(timeout=3)
        self.server.server_close()
