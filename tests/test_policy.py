from __future__ import annotations

import logging
import unittest

from doubleagent.config import Config, LoadedConfig, resolve_secrets
from doubleagent.policy import check_block, inject_request_secrets


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("doubleagent.tests")
        config = Config.model_validate(
            {
                "rules": [
                    {
                        "domains": ["api.example.com"],
                        "secrets": [
                            {
                                "placeholder": "PLACEHOLDER_KEY",
                                "value": "real-secret",
                                "inject_in": ["header:authorization", "query:api_key", "body"],
                                "prefix": "Bearer ",
                            }
                        ],
                        "block": [
                            {
                                "method": "DELETE",
                                "path_pattern": "/admin/**",
                                "response": {
                                    "status": 403,
                                    "body": {"error": "blocked"},
                                },
                            }
                        ],
                        "allow": [{"method": "DELETE", "path_pattern": "/admin/safe"}],
                    }
                ],
                "default_policy": "allow",
                "allow_http_secret_injection": True,
            }
        )
        self.loaded = LoadedConfig(config=config, resolved_secrets=resolve_secrets(config))

    def test_block_rule(self) -> None:
        blocked = check_block(self.loaded, "api.example.com", "DELETE", "/admin/users/1")
        self.assertIsNotNone(blocked)
        assert blocked is not None
        self.assertEqual(blocked.status, 403)

    def test_allow_overrides_block(self) -> None:
        allowed = check_block(self.loaded, "api.example.com", "DELETE", "/admin/safe")
        self.assertIsNone(allowed)

    def test_secret_injection(self) -> None:
        headers = {"authorization": "PLACEHOLDER_KEY"}
        query = {"api_key": "PLACEHOLDER_KEY"}
        body = b'{"key":"PLACEHOLDER_KEY"}'
        new_body = inject_request_secrets(
            self.loaded,
            "api.example.com",
            "https",
            headers,
            query,
            body,
            self.logger,
        )
        self.assertIsNotNone(new_body)
        assert new_body is not None
        self.assertEqual(headers["authorization"], "Bearer real-secret")
        self.assertEqual(query["api_key"], "Bearer real-secret")
        self.assertIn(b"Bearer real-secret", new_body)


if __name__ == "__main__":
    unittest.main()
