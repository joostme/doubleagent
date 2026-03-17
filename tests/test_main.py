from __future__ import annotations

import argparse
import unittest
from unittest.mock import ANY, Mock, patch

from doubleagent import main


class MainTests(unittest.TestCase):
    @patch("doubleagent.main.signal.signal")
    @patch("doubleagent.main.export_generated_ca")
    @patch("doubleagent.main.subprocess.Popen")
    @patch("doubleagent.main.build_mitmdump_command", return_value=["mitmdump"])
    @patch("doubleagent.main.HealthServer")
    @patch("doubleagent.main.prepare_confdir")
    @patch("doubleagent.main.resolve_secrets")
    @patch("doubleagent.main.load_config")
    @patch("doubleagent.main.parse_args")
    def test_main_starts_explicit_proxy(
        self,
        mock_parse_args: Mock,
        mock_load_config: Mock,
        mock_resolve_secrets: Mock,
        mock_prepare_confdir: Mock,
        mock_health_server: Mock,
        mock_build_mitmdump_command: Mock,
        mock_popen: Mock,
        mock_export_generated_ca: Mock,
        mock_signal: Mock,
    ) -> None:
        mock_parse_args.return_value = argparse.Namespace(
            config="/tmp/config.json",
        )
        mock_load_config.return_value = argparse.Namespace(
            log_level="info",
            default_policy="allow",
            rules=[],
            ca=argparse.Namespace(cert_path="/tmp/ca.crt"),
            health_port=9000,
            http_port=8080,
        )
        mock_prepare_confdir.return_value = "/tmp/confdir"

        health_server = Mock()
        mock_health_server.return_value = health_server

        child = Mock()
        child.wait.return_value = 0
        mock_popen.return_value = child

        self.assertEqual(main.main(), 0)

        mock_resolve_secrets.assert_called_once()
        mock_build_mitmdump_command.assert_called_once_with(8080, "/tmp/confdir")
        mock_popen.assert_called_once_with(["mitmdump"], env=ANY)
        mock_export_generated_ca.assert_called_once_with("/tmp/confdir", "/tmp/ca.crt", ANY)
        child.wait.assert_called_once_with()
        mock_health_server.return_value.start.assert_called_once()
        health_server.stop.assert_called_once()
        self.assertEqual(mock_signal.call_count, 2)

    @patch("doubleagent.main.signal.signal")
    @patch("doubleagent.main.export_generated_ca")
    @patch("doubleagent.main.subprocess.Popen")
    @patch("doubleagent.main.build_mitmdump_command", return_value=["mitmdump"])
    @patch("doubleagent.main.HealthServer")
    @patch("doubleagent.main.prepare_confdir")
    @patch("doubleagent.main.resolve_secrets")
    @patch("doubleagent.main.load_config")
    @patch("doubleagent.main.parse_args")
    def test_main_stops_child_when_ca_export_fails(
        self,
        mock_parse_args: Mock,
        mock_load_config: Mock,
        mock_resolve_secrets: Mock,
        mock_prepare_confdir: Mock,
        mock_health_server: Mock,
        mock_build_mitmdump_command: Mock,
        mock_popen: Mock,
        mock_export_generated_ca: Mock,
        mock_signal: Mock,
    ) -> None:
        mock_parse_args.return_value = argparse.Namespace(
            config="/tmp/config.json",
        )
        mock_load_config.return_value = argparse.Namespace(
            log_level="info",
            default_policy="allow",
            rules=[],
            ca=argparse.Namespace(cert_path="/tmp/ca.crt"),
            health_port=9000,
            http_port=8080,
        )
        mock_prepare_confdir.return_value = "/tmp/confdir"
        health_server = Mock()
        mock_health_server.return_value = health_server

        child = Mock()
        mock_popen.return_value = child

        mock_export_generated_ca.side_effect = TimeoutError("ca export failed")

        with self.assertRaisesRegex(TimeoutError, "ca export failed"):
            main.main()

        child.terminate.assert_called_once()
        child.wait.assert_called_once_with(timeout=5)
        health_server.stop.assert_called_once()
        mock_signal.assert_not_called()


if __name__ == "__main__":
    unittest.main()
