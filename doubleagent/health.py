from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _healthcheck_response(path: str, ready_event: threading.Event) -> tuple[int, dict[str, str]]:
    if path == "/healthz":
        return 200, {"status": "alive"}
    if path == "/readyz":
        if ready_event.is_set():
            return 200, {"status": "ready"}
        return 503, {"status": "not_ready"}
    return 404, {"error": "not_found"}


def _write_json_response(
    handler: BaseHTTPRequestHandler,
    status_code: int,
    body: dict[str, str],
) -> None:
    payload = json.dumps(body).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


class HealthServer:
    def __init__(self, port: int, ready_event: threading.Event):
        self.port = port
        self.ready_event = ready_event
        self._server = ThreadingHTTPServer(("0.0.0.0", port), self._make_handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _make_handler(self):
        ready_event = self.ready_event

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                status_code, body = _healthcheck_response(self.path, ready_event)
                _write_json_response(self, status_code, body)

            def log_message(self, format: str, *args) -> None:  # noqa: A003
                return

        return Handler

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
