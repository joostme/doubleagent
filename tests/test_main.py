from __future__ import annotations

import argparse
import unittest
from unittest.mock import ANY, Mock, patch

from doubleagent import main


_PATCHES = [
    "doubleagent.main.signal.signal",
    "doubleagent.main.export_generated_ca",
    "doubleagent.main.subprocess.Popen",
    "doubleagent.main.build_mitmdump_command",
    "doubleagent.main.HealthServer",
    "doubleagent.main.prepare_confdir",
    "doubleagent.main.resolve_secrets",
    "doubleagent.main.load_config",
    "doubleagent.main.parse_args",
]


def _apply_main_patches(func):
    """Apply the standard set of patches for main() tests.

    Patches are applied in reverse so that the argument order matches
    stacking @patch decorators from top (outermost) to bottom (innermost).
    """
    for target in reversed(_PATCHES):
        func = patch(target)(func)
    return func


def _configure_standard_mocks(
    mock_parse_args: Mock,
    mock_load_config: Mock,
    mock_prepare_confdir: Mock,
    mock_build_mitmdump_command: Mock,
    mock_health_server: Mock,
) -> Mock:
    """Set up the common mock return values used by all main() tests.

    Returns the health_server mock instance.
    """
    mock_parse_args.return_value = argparse.Namespace(config="/tmp/config.json")
    mock_load_config.return_value = argparse.Namespace(
        log_level="info",
        default_policy="allow",
        rules=[],
        forward_ports=[],
        ca=argparse.Namespace(cert_path="/tmp/ca.crt"),
        health_port=9000,
        http_port=8080,
    )
    mock_prepare_confdir.return_value = "/tmp/confdir"
    mock_build_mitmdump_command.return_value = ["mitmdump"]

    health_server = Mock()
    mock_health_server.return_value = health_server
    return health_server


class MainTests(unittest.TestCase):
    @_apply_main_patches
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
        health_server = _configure_standard_mocks(
            mock_parse_args, mock_load_config, mock_prepare_confdir,
            mock_build_mitmdump_command, mock_health_server,
        )

        child = Mock()
        child.wait.return_value = 0
        mock_popen.return_value = child

        self.assertEqual(main.main(), 0)

        mock_resolve_secrets.assert_called_once()
        mock_build_mitmdump_command.assert_called_once_with(8080, "/tmp/confdir")
        mock_popen.assert_called_once_with(["mitmdump"], env=ANY)
        mock_export_generated_ca.assert_called_once_with("/tmp/confdir", "/tmp/ca.crt", ANY)
        child.wait.assert_called_once_with()
        health_server.start.assert_called_once()
        health_server.stop.assert_called_once()
        self.assertEqual(mock_signal.call_count, 2)

    @_apply_main_patches
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
        health_server = _configure_standard_mocks(
            mock_parse_args, mock_load_config, mock_prepare_confdir,
            mock_build_mitmdump_command, mock_health_server,
        )

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
