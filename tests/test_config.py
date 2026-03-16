from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from doubleagent.config import Config, load_config, match_domain, match_path, resolve_secrets
from doubleagent.logging_utils import resolve_log_level


class ConfigTests(unittest.TestCase):
    def _write_config(self, payload: str) -> str:
        tmpdir = tempfile.mkdtemp(prefix="doubleagent-config-")
        path = Path(tmpdir) / "config.json"
        path.write_text(payload, encoding="utf-8")
        return str(path)

    def test_load_config_defaults(self) -> None:
        path = self._write_config('{"rules": []}')
        config = load_config(path)
        self.assertEqual(config.log_level, "info")
        self.assertEqual(config.default_policy, "allow")
        self.assertEqual(config.http_port, 8080)
        self.assertFalse(config.allow_http_secret_injection)

    def test_match_domain(self) -> None:
        self.assertTrue(match_domain("api.openai.com", ["api.openai.com"]))
        self.assertTrue(match_domain("deep.sub.example.com", ["*.example.com"]))
        self.assertFalse(match_domain("example.com", ["*.example.com"]))

    def test_match_path(self) -> None:
        self.assertTrue(match_path("/v1/files/abc", "/v1/files/*"))
        self.assertFalse(match_path("/v1/files/abc/def", "/v1/files/*"))
        self.assertTrue(match_path("/v1/files/abc/def", "/v1/files/**"))

    def test_resolve_secrets_from_env(self) -> None:
        os.environ["TEST_KEY"] = "secret-value"
        path = self._write_config(
            '{"rules": [{"domains": ["x.com"], "secrets": [{"placeholder": "PH", "value_from_env": "TEST_KEY", "inject_in": ["body"]}]}]}'
        )
        config = load_config(path)
        resolved = resolve_secrets(config)
        self.assertEqual(resolved[0][0].resolved_value, "secret-value")

    def test_resolve_log_level_accepts_warning(self) -> None:
        self.assertEqual(resolve_log_level("warning"), 30)
        self.assertEqual(resolve_log_level("debug"), 10)

    def test_load_config_accepts_warning_log_level(self) -> None:
        path = self._write_config('{"log_level": "warning", "rules": []}')
        config = load_config(path)
        self.assertEqual(config.log_level, "warning")

    def test_load_config_accepts_boolean_allow_and_block_rules(self) -> None:
        path = self._write_config(
            '{"rules": [{"domains": ["allow.example.com"], "allow": true}, {"domains": ["block.example.com"], "block": true}]}'
        )
        config = load_config(path)
        self.assertTrue(config.rules[0].allow)
        self.assertTrue(config.rules[1].block)

    def test_rule_rejects_both_allow_and_block_true(self) -> None:
        with self.assertRaises(ValidationError):
            Config.model_validate(
                {"rules": [{"domains": ["example.com"], "allow": True, "block": True}]}
            )


if __name__ == "__main__":
    unittest.main()
