from __future__ import annotations

import unittest
import tempfile
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch
from pathlib import Path

from mitmproxy.tls import ClientHelloData

from doubleagent.config import Config, LoadedConfig, resolve_secrets


class AddonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="doubleagent-addon-")
        cls._config_path = Path(cls._tmpdir.name) / "config.json"
        cls._config_path.write_text('{"rules": []}', encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def _loaded_config(self, policy: str) -> LoadedConfig:
        config = Config.model_validate(
            {
                "rules": [{"domains": ["pinned.example.com"], "policy": policy}],
                "default_policy": "allow",
            }
        )
        return LoadedConfig(config=config, resolved_secrets=resolve_secrets(config))

    def test_tls_clienthello_bypasses_pinned_domain(self) -> None:
        with patch.dict("os.environ", {"DOUBLEAGENT_CONFIG": str(self._config_path)}):
            from doubleagent.addon import DoubleAgentAddon

            with patch("doubleagent.addon.ConfigStore") as mock_config_store:
                mock_store = Mock()
                mock_store.get.return_value = self._loaded_config("bypass")
                mock_config_store.return_value = mock_store

                addon = DoubleAgentAddon()
                data = SimpleNamespace(
                    client_hello=SimpleNamespace(sni="pinned.example.com"),
                    ignore_connection=False,
                )

                addon.tls_clienthello(cast(ClientHelloData, data))

                self.assertTrue(data.ignore_connection)

    def test_tls_clienthello_keeps_interception_for_allowed_domain(self) -> None:
        with patch.dict("os.environ", {"DOUBLEAGENT_CONFIG": str(self._config_path)}):
            from doubleagent.addon import DoubleAgentAddon

            with patch("doubleagent.addon.ConfigStore") as mock_config_store:
                mock_store = Mock()
                mock_store.get.return_value = self._loaded_config("allow")
                mock_config_store.return_value = mock_store

                addon = DoubleAgentAddon()
                data = SimpleNamespace(
                    client_hello=SimpleNamespace(sni="pinned.example.com"),
                    ignore_connection=False,
                )

                addon.tls_clienthello(cast(ClientHelloData, data))

                self.assertFalse(data.ignore_connection)


if __name__ == "__main__":
    unittest.main()
