from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


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
                body: dict[str, str]
                if self.path == "/healthz":
                    self.send_response(200)
                    body = {"status": "alive"}
                elif self.path == "/readyz":
                    if ready_event.is_set():
                        self.send_response(200)
                        body = {"status": "ready"}
                    else:
                        self.send_response(503)
                        body = {"status": "not_ready"}
                else:
                    self.send_response(404)
                    body = {"error": "not_found"}

                payload = json.dumps(body).encode("utf-8")
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args) -> None:  # noqa: A003
                return

        return Handler

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
