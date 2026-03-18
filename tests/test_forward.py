from __future__ import annotations

import shutil
import socket
import subprocess
import time
import unittest
from unittest.mock import Mock, patch

from doubleagent.forward import ForwardTarget, PortForwarder, _build_socat_command


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestBuildSocatCommand(unittest.TestCase):
    def test_default_listen_host(self) -> None:
        target = ForwardTarget(listen_port=3000, target_host="ai-agent", target_port=8080)
        cmd = _build_socat_command(target)
        self.assertEqual(cmd, [
            "socat",
            "TCP-LISTEN:3000,bind=0.0.0.0,reuseaddr,fork",
            "TCP:ai-agent:8080",
        ])

    def test_debug_log_level_enables_verbose_socat_logging(self) -> None:
        target = ForwardTarget(listen_port=3000, target_host="ai-agent", target_port=8080)
        cmd = _build_socat_command(target, log_level="debug")
        self.assertEqual(cmd, [
            "socat",
            "-dddd",
            "TCP-LISTEN:3000,bind=0.0.0.0,reuseaddr,fork",
            "TCP:ai-agent:8080",
        ])

    def test_error_log_level_suppresses_socat_warnings(self) -> None:
        target = ForwardTarget(listen_port=3000, target_host="ai-agent", target_port=8080)
        cmd = _build_socat_command(target, log_level="error")
        self.assertEqual(cmd, [
            "socat",
            "-d0",
            "TCP-LISTEN:3000,bind=0.0.0.0,reuseaddr,fork",
            "TCP:ai-agent:8080",
        ])

    def test_custom_listen_host(self) -> None:
        target = ForwardTarget(listen_port=4000, target_host="backend", target_port=5000)
        cmd = _build_socat_command(target, listen_host="127.0.0.1")
        self.assertEqual(cmd, [
            "socat",
            "TCP-LISTEN:4000,bind=127.0.0.1,reuseaddr,fork",
            "TCP:backend:5000",
        ])


class TestPortForwarderLifecycle(unittest.TestCase):
    def test_start_stop_no_targets(self) -> None:
        forwarder = PortForwarder([])
        forwarder.start()
        forwarder.stop()
        self.assertEqual(len(forwarder._processes), 0)

    @patch("doubleagent.forward.subprocess.Popen")
    def test_start_spawns_socat_processes(self, mock_popen: Mock) -> None:
        proc = Mock()
        mock_popen.return_value = proc

        targets = [
            ForwardTarget(listen_port=3000, target_host="ai-agent", target_port=3000),
            ForwardTarget(listen_port=4000, target_host="ai-agent", target_port=4000),
        ]
        forwarder = PortForwarder(targets)
        forwarder.start()

        self.assertEqual(mock_popen.call_count, 2)
        self.assertEqual(len(forwarder._processes), 2)

        # Verify the socat commands
        calls = mock_popen.call_args_list
        self.assertEqual(calls[0].args[0], [
            "socat",
            "TCP-LISTEN:3000,bind=0.0.0.0,reuseaddr,fork",
            "TCP:ai-agent:3000",
        ])
        self.assertEqual(calls[1].args[0], [
            "socat",
            "TCP-LISTEN:4000,bind=0.0.0.0,reuseaddr,fork",
            "TCP:ai-agent:4000",
        ])

    @patch("doubleagent.forward.subprocess.Popen")
    def test_start_passes_debug_logging_to_socat(self, mock_popen: Mock) -> None:
        proc = Mock()
        mock_popen.return_value = proc

        forwarder = PortForwarder([
            ForwardTarget(listen_port=3000, target_host="ai-agent", target_port=3000),
        ], log_level="debug")
        forwarder.start()

        mock_popen.assert_called_once_with([
            "socat",
            "-dddd",
            "TCP-LISTEN:3000,bind=0.0.0.0,reuseaddr,fork",
            "TCP:ai-agent:3000",
        ])

    @patch("doubleagent.forward.subprocess.Popen")
    def test_stop_terminates_processes(self, mock_popen: Mock) -> None:
        proc = Mock()
        mock_popen.return_value = proc

        forwarder = PortForwarder([
            ForwardTarget(listen_port=3000, target_host="ai-agent", target_port=3000),
        ])
        forwarder.start()
        forwarder.stop()

        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=5)
        self.assertEqual(len(forwarder._processes), 0)

    @patch("doubleagent.forward.subprocess.Popen")
    def test_stop_kills_on_timeout(self, mock_popen: Mock) -> None:
        proc = Mock()
        proc.pid = 12345
        proc.wait.side_effect = [subprocess.TimeoutExpired("socat", 5), None]
        mock_popen.return_value = proc

        forwarder = PortForwarder([
            ForwardTarget(listen_port=3000, target_host="ai-agent", target_port=3000),
        ])
        forwarder.start()
        forwarder.stop()

        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()

    @patch("doubleagent.forward.subprocess.Popen")
    def test_stop_handles_already_exited(self, mock_popen: Mock) -> None:
        proc = Mock()
        proc.terminate.side_effect = ProcessLookupError
        mock_popen.return_value = proc

        forwarder = PortForwarder([
            ForwardTarget(listen_port=3000, target_host="ai-agent", target_port=3000),
        ])
        forwarder.start()
        forwarder.stop()

        proc.terminate.assert_called_once()
        proc.wait.assert_not_called()


@unittest.skipUnless(shutil.which("socat"), "socat not installed")
class TestPortForwarderIntegration(unittest.TestCase):
    """Live tests that require socat to be installed."""

    def _echo_server(self, port: int) -> subprocess.Popen[bytes]:
        """Start a socat echo server on the given port."""
        proc = subprocess.Popen([
            "socat",
            f"TCP-LISTEN:{port},reuseaddr,fork",
            "EXEC:cat",
        ])
        time.sleep(0.3)
        return proc

    def test_tcp_round_trip(self) -> None:
        target_port = _get_free_port()
        listen_port = _get_free_port()

        echo = self._echo_server(target_port)
        try:
            forwarder = PortForwarder([
                ForwardTarget(listen_port=listen_port, target_host="127.0.0.1", target_port=target_port),
            ])
            forwarder.start()
            time.sleep(0.3)

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                sock.connect(("127.0.0.1", listen_port))
                sock.sendall(b"hello doubleagent")
                data = sock.recv(4096)
                sock.close()
                self.assertEqual(data, b"hello doubleagent")
            finally:
                forwarder.stop()
        finally:
            echo.terminate()
            echo.wait(timeout=3)


class TestForwardPortConfig(unittest.TestCase):
    def test_forward_ports_default_empty(self) -> None:
        from doubleagent.config import Config

        config = Config.model_validate({"rules": []})
        self.assertEqual(config.forward_ports, [])

    def test_forward_ports_valid(self) -> None:
        from doubleagent.config import Config

        config = Config.model_validate(
            {
                "rules": [],
                "forward_ports": [
                    {"listen_port": 3000, "target_host": "ai-agent", "target_port": 3000}
                ],
            }
        )
        self.assertEqual(len(config.forward_ports), 1)
        self.assertEqual(config.forward_ports[0].listen_port, 3000)
        self.assertEqual(config.forward_ports[0].target_host, "ai-agent")
        self.assertEqual(config.forward_ports[0].target_port, 3000)

    def test_forward_ports_rejects_invalid_port(self) -> None:
        from pydantic import ValidationError

        from doubleagent.config import Config

        with self.assertRaises(ValidationError):
            Config.model_validate(
                {
                    "rules": [],
                    "forward_ports": [
                        {"listen_port": 0, "target_host": "ai-agent", "target_port": 3000}
                    ],
                }
            )

    def test_forward_ports_rejects_empty_host(self) -> None:
        from pydantic import ValidationError

        from doubleagent.config import Config

        with self.assertRaises(ValidationError):
            Config.model_validate(
                {
                    "rules": [],
                    "forward_ports": [
                        {"listen_port": 3000, "target_host": "", "target_port": 3000}
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
