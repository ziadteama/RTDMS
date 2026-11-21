"""HTTP server adapter for incident routes."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .http_routes import handle
from .sink import IncidentReporter
from .store import IncidentStore


def make_incident_handler(
    store: IncidentStore,
    reporter: IncidentReporter,
    token: str,
) -> type[BaseHTTPRequestHandler]:
    class IncidentHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass  # never log incident payloads or secrets

        def _send(
            self, code: int, hdrs: dict[str, str], body: bytes | Iterator[bytes] | Path
        ) -> None:
            self.send_response(code)
            for k, v in hdrs.items():
                self.send_header(k, v)
            self.end_headers()
            if isinstance(body, bytes):
                self.wfile.write(body)
            elif isinstance(body, Path):
                with open(body, "rb") as f:
                    while chunk := f.read(65536):
                        self.wfile.write(chunk)
            elif hasattr(body, "__iter__"):
                for chunk in body:
                    self.wfile.write(chunk)

        def do_GET(self) -> None:
            headers = {k: v for k, v in self.headers.items()}
            code, hdrs, body = handle("GET", self.path, headers, b"", store, reporter, token)
            self._send(code, hdrs, body)

        def do_POST(self) -> None:
            headers = {k: v for k, v in self.headers.items()}
            length = int(self.headers.get("Content-Length", "0"))
            body_bytes = self.rfile.read(length) if length > 0 else b""
            code, hdrs, body = handle(
                "POST", self.path, headers, body_bytes, store, reporter, token
            )
            self._send(code, hdrs, body)

        def setup(self) -> None:
            self.request.settimeout(10)
            super().setup()

    return IncidentHandler


class IncidentServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        store: IncidentStore,
        reporter: IncidentReporter,
        token: str,
    ) -> None:
        self.address_family = socket.AF_INET6 if ":" in server_address[0] else socket.AF_INET
        handler_cls = make_incident_handler(store, reporter, token)
        super().__init__(server_address, handler_cls)
        self._thread = threading.Thread(
            target=self.serve_forever, daemon=True, name="incident-http"
        )

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        if self._thread.is_alive():
            self.shutdown()
            self._thread.join(timeout=3)
        self.server_close()


def serve(
    host: str,
    port: int,
    store: IncidentStore,
    reporter: IncidentReporter,
    token: str,
    start: bool = True,
) -> IncidentServer:
    server = IncidentServer((host, port), store, reporter, token)
    if start:
        server.start()
    return server
