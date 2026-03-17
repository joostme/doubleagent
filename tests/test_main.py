from __future__ import annotations

import argparse
import unittest
from unittest.mock import ANY, Mock, patch

from doubleagent import main


class MainTests(unittest.TestCase):
    @patch("doubleagent.main.signal.signal")
    @patch("doubleagent.main.export_generated_ca")
    @patch("doubleagent.main.add_pid_to_cgroup")
    @patch("doubleagent.main.subprocess.Popen")
    @patch("doubleagent.main.build_mitmdump_command", return_value=["mitmdump"])
    @patch("doubleagent.main.remove_cgroup")
    @patch("doubleagent.main.cleanup_iptables")
    @patch("doubleagent.main.setup_iptables")
    @patch("doubleagent.main.build_proxy_cgroup_path", return_value="/doubleagent-proxy")
    @patch("doubleagent.main.get_process_cgroup_path", return_value="/")
    @patch("doubleagent.main.HealthServer")
    @patch("doubleagent.main.prepare_confdir")
    @patch("doubleagent.main.resolve_secrets")
    @patch("doubleagent.main.load_config")
    @patch("doubleagent.main.parse_args")
    def test_main_reports_actionable_cgroup_error(
        self,
        mock_parse_args: Mock,
        mock_load_config: Mock,
        mock_resolve_secrets: Mock,
        mock_prepare_confdir: Mock,
        mock_health_server: Mock,
        mock_get_process_cgroup_path: Mock,
        mock_build_proxy_cgroup_path: Mock,
        mock_setup_iptables: Mock,
        mock_cleanup_iptables: Mock,
        mock_remove_cgroup: Mock,
        mock_build_mitmdump_command: Mock,
        mock_popen: Mock,
        mock_add_pid_to_cgroup: Mock,
        mock_export_generated_ca: Mock,
        mock_signal: Mock,
    ) -> None:
        mock_parse_args.return_value = argparse.Namespace(
            config="/tmp/config.json",
            skip_iptables=False,
            cleanup_iptables=False,
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
        child.pid = 1234
        mock_popen.return_value = child

        mock_add_pid_to_cgroup.side_effect = OSError("read-only file system")

        with self.assertRaisesRegex(RuntimeError, "cgroup v2 delegation"):
            main.main()

        child.terminate.assert_called_once()
        child.wait.assert_called_once_with(timeout=5)
        health_server.stop.assert_called_once()
        mock_export_generated_ca.assert_not_called()
        mock_signal.assert_not_called()
        mock_build_proxy_cgroup_path.assert_called_once_with("/")
        mock_cleanup_iptables.assert_called_once()
        mock_remove_cgroup.assert_called_once_with("/doubleagent-proxy")
        mock_setup_iptables.assert_called_once_with(8080, "/doubleagent-proxy", ANY)


if __name__ == "__main__":
    unittest.main()
