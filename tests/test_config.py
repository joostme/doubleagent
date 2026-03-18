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
        tmpdir = tempfile.TemporaryDirectory(prefix="doubleagent-config-")
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "config.json"
        path.write_text(payload, encoding="utf-8")
        return str(path)

    def test_load_config_defaults(self) -> None:
        path = self._write_config('{"rules": []}')
        config = load_config(path)
        self.assertEqual(config.log_level, "info")
        self.assertEqual(config.default_policy, "allow")
        self.assertEqual(config.http_port, 8080)

    def test_match_domain(self) -> None:
        self.assertTrue(match_domain("api.openai.com", ["api.openai.com"]))
        self.assertTrue(match_domain("deep.sub.example.com", [".example.com"]))
        self.assertFalse(match_domain("example.com", [".example.com"]))
        self.assertTrue(match_domain("deep.sub.example.com", ["*.example.com"]))

    def test_match_path(self) -> None:
        self.assertTrue(match_path("/v1/files/abc", "/v1/files/*"))
        self.assertFalse(match_path("/v1/files/abc/def", "/v1/files/*"))
        self.assertTrue(match_path("/v1/files/abc/def", "/v1/files/**"))
        self.assertTrue(match_path("/v1/files/report.json", "/v1/files/*.json"))

    def test_resolve_secrets_from_env(self) -> None:
        self.addCleanup(os.environ.pop, "TEST_KEY", None)
        os.environ["TEST_KEY"] = "secret-value"
        path = self._write_config(
            '{"rules": [{"domains": ["x.com"], "secrets": [{"placeholder": "PH", "value_from_env": "TEST_KEY", "inject_in": ["header:Authorization"]}]}]}'
        )
        config = load_config(path)
        resolved = resolve_secrets(config)
        self.assertEqual(resolved[0][0].resolved_value, "secret-value")

    def test_rejects_body_secret_injection(self) -> None:
        with self.assertRaises(ValidationError):
            Config.model_validate(
                {
                    "rules": [
                        {
                            "domains": ["x.com"],
                            "secrets": [{"placeholder": "PH", "value": "secret", "inject_in": ["body"]}],
                        }
                    ]
                }
            )

    def test_resolve_log_level_accepts_warning(self) -> None:
        self.assertEqual(resolve_log_level("warning"), 30)
        self.assertEqual(resolve_log_level("debug"), 10)

    def test_load_config_accepts_warning_log_level(self) -> None:
        path = self._write_config('{"log_level": "warning", "rules": []}')
        config = load_config(path)
        self.assertEqual(config.log_level, "warning")

    def test_load_config_accepts_rule_policy(self) -> None:
        path = self._write_config(
            '{"rules": [{"domains": ["allow.example.com"], "policy": "allow"}, {"domains": ["block.example.com"], "policy": "block"}]}'
        )
        config = load_config(path)
        self.assertEqual(config.rules[0].policy, "allow")
        self.assertEqual(config.rules[1].policy, "block")

    def test_load_config_accepts_nested_request_rules(self) -> None:
        path = self._write_config(
            '{"rules": [{"domains": ["api.example.com"], "rules": [{"policy": "block", "method": "DELETE", "path_pattern": "/admin/**", "response": {"status": 403, "body": {"error": "blocked"}}}, {"policy": "allow", "method": "DELETE", "path_pattern": "/admin/safe"}]}]}'
        )
        config = load_config(path)
        self.assertEqual(config.rules[0].rules[0].policy, "block")
        self.assertEqual(config.rules[0].rules[1].policy, "allow")

    def test_load_config_rejects_unknown_root_field(self) -> None:
        path = self._write_config('{"rules": [], "unexpected": true}')
        with self.assertRaises(ValidationError):
            load_config(path)

    def test_rule_rejects_invalid_policy(self) -> None:
        with self.assertRaises(ValidationError):
            Config.model_validate({"rules": [{"domains": ["example.com"], "policy": "deny"}]})

    def test_request_rule_rejects_block_without_response(self) -> None:
        with self.assertRaises(ValidationError):
            Config.model_validate(
                {
                    "rules": [
                        {
                            "domains": ["example.com"],
                            "rules": [
                                {
                                    "policy": "block",
                                    "path_pattern": "/admin/**",
                                }
                            ],
                        }
                    ]
                }
            )

    def test_request_rule_rejects_allow_with_response(self) -> None:
        with self.assertRaises(ValidationError):
            Config.model_validate(
                {
                    "rules": [
                        {
                            "domains": ["example.com"],
                            "rules": [
                                {
                                    "policy": "allow",
                                    "path_pattern": "/admin/safe",
                                    "response": {"status": 200, "body": {"ok": True}},
                                }
                            ],
                        }
                    ]
                }
            )

    def test_secret_rejects_both_value_and_value_from_env(self) -> None:
        with self.assertRaises(ValidationError):
            Config.model_validate(
                {
                    "rules": [
                        {
                            "domains": ["x.com"],
                            "secrets": [
                                {
                                    "placeholder": "PH",
                                    "value": "inline-secret",
                                    "value_from_env": "SOME_VAR",
                                    "inject_in": ["header:Authorization"],
                                }
                            ],
                        }
                    ]
                }
            )


if __name__ == "__main__":
    unittest.main()
