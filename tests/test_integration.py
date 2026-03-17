from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import textwrap
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class EchoHandler(BaseHTTPRequestHandler):
    def _send_json_response(self, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _drain_request_body(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length:
            self.rfile.read(content_length)

    def do_GET(self) -> None:  # noqa: N802
        self._send_json_response({
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers),
        })

    def do_POST(self) -> None:  # noqa: N802
        self._drain_request_body()
        self._send_json_response({
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers),
        })

    def do_DELETE(self) -> None:  # noqa: N802
        self._send_json_response({"method": self.command, "path": self.path})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class MitmproxyIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(prefix="doubleagent-integration-")
        self.proxy_port = free_port()
        self.upstream_port = free_port()

        self.upstream = ThreadingHTTPServer(("127.0.0.1", self.upstream_port), EchoHandler)
        self.upstream_thread = Thread(target=self.upstream.serve_forever, daemon=True)
        self.upstream_thread.start()

        self.config_path = Path(self.tmpdir.name) / "config.json"
        self.confdir = Path(self.tmpdir.name) / "mitmconf"
        self.confdir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            textwrap.dedent(
                f"""
                {{
                  "rules": [
                    {{
                      "domains": ["localhost"],
                      "secrets": [
                        {{
                          "placeholder": "PLACEHOLDER_KEY",
                          "value": "real-secret-value",
                          "inject_in": ["header:Authorization", "query:api_key"]
                        }}
                      ],
                      "block": [
                        {{
                          "method": "DELETE",
                          "path_pattern": "/admin/**",
                          "response": {{
                            "status": 403,
                            "body": {{"error": "blocked", "reason": "not allowed"}}
                          }}
                        }}
                      ],
                      "allow": [
                        {{
                          "method": "DELETE",
                          "path_pattern": "/admin/safe"
                        }}
                      ]
                    }}
                  ],
                  "default_policy": "allow"
                }}
                """
            ).strip(),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["DOUBLEAGENT_CONFIG"] = str(self.config_path)
        env["PYTHONPATH"] = "/repos/aivpn"

        self.proc = subprocess.Popen(
            [
                "mitmdump",
                "--mode",
                "regular",
                "--listen-host",
                "127.0.0.1",
                "--listen-port",
                str(self.proxy_port),
                "-s",
                "/repos/aivpn/doubleagent/addon.py",
                "--set",
                f"confdir={self.confdir}",
                "--set",
                "block_global=false",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._wait_for_proxy()

    def tearDown(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.upstream.shutdown()
        self.upstream.server_close()
        self.upstream_thread.join(timeout=5)
        self.tmpdir.cleanup()

    def _wait_for_proxy(self) -> None:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.proxy_port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("mitmdump did not start in time")

    def _request(self, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None):
        req = urllib.request.Request(
            f"http://localhost:{self.upstream_port}{path}",
            data=body,
            headers=headers or {},
            method=method,
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{self.proxy_port}"})
        )
        return opener.open(req, timeout=10)

    def test_blocks_matching_request(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._request("DELETE", "/admin/users/1")
        self.assertEqual(cm.exception.code, 403)
        payload = json.loads(cm.exception.read().decode("utf-8"))
        self.assertEqual(payload["error"], "blocked")

    def test_injects_secret_in_header_and_query(self) -> None:
        response = self._request(
            "POST",
            "/v1/test?api_key=PLACEHOLDER_KEY",
            body=b'{"key":"PLACEHOLDER_KEY"}',
            headers={"Authorization": "Bearer PLACEHOLDER_KEY", "Content-Type": "application/json"},
        )
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["headers"]["Authorization"], "Bearer real-secret-value")
        self.assertIn("api_key=real-secret-value", payload["path"])


if __name__ == "__main__":
    unittest.main()
