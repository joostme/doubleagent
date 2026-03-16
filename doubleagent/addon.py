from __future__ import annotations

import json
import logging
import os

from mitmproxy import http

from doubleagent.config import ConfigStore
from doubleagent.policy import check_block, inject_request_secrets


LOGGER = logging.getLogger("doubleagent.addon")
CONFIG_PATH = os.environ.get("DOUBLEAGENT_CONFIG", "/config/config.json")


class DoubleAgentAddon:
    def __init__(self) -> None:
        self.store = ConfigStore(CONFIG_PATH, LOGGER)

    def request(self, flow: http.HTTPFlow) -> None:
        loaded = self.store.get()
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

        new_body = inject_request_secrets(
            loaded=loaded,
            hostname=host,
            scheme=flow.request.scheme,
            headers=flow.request.headers,
            query=flow.request.query,
            body=flow.request.content,
            logger=LOGGER,
        )
        if new_body is not None and new_body != flow.request.content:
            flow.request.content = new_body


addons = [DoubleAgentAddon()]
