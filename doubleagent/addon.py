from __future__ import annotations

import json
import logging
import os

from mitmproxy import http

from doubleagent.config import ConfigStore
from doubleagent.logging_utils import set_logger_level
from doubleagent.policy import check_block, inject_request_secrets


LOGGER = logging.getLogger("doubleagent.addon")
CONFIG_PATH = os.environ.get("DOUBLEAGENT_CONFIG", "/config/config.json")


class DoubleAgentAddon:
    def __init__(self) -> None:
        self.store = ConfigStore(CONFIG_PATH, LOGGER)
        set_logger_level(LOGGER, self.store.get().config.log_level)

    def request(self, flow: http.HTTPFlow) -> None:
        loaded = self.store.get()
        set_logger_level(LOGGER, loaded.config.log_level)
        host = flow.request.pretty_host or flow.request.host or ""
        path = flow.request.path.split("?", 1)[0]
        method = flow.request.method

        block = check_block(loaded, host, method, path)
        if block is not None:
            body = json.dumps(block.body).encode("utf-8")
            flow.response = http.Response.make(
                block.status,
                body,
                {
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "X-Doubleagent-Blocked": "true",
                },
            )
            return

        inject_request_secrets(
            loaded=loaded,
            hostname=host,
            scheme=flow.request.scheme,
            headers=flow.request.headers,
            query=flow.request.query,
            logger=LOGGER,
        )


addons = [DoubleAgentAddon()]
