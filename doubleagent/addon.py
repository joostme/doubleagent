from __future__ import annotations

import json
import logging
import os

from mitmproxy import http

from doubleagent.config import BlockResponse, ConfigStore, DEFAULT_CONFIG_PATH
from doubleagent.logging_utils import set_logger_level
from doubleagent.policy import check_block, inject_request_secrets


LOGGER = logging.getLogger("doubleagent.addon")
CONFIG_PATH = os.environ.get("DOUBLEAGENT_CONFIG", DEFAULT_CONFIG_PATH)


class DoubleAgentAddon:
    def __init__(self) -> None:
        self.store = ConfigStore(CONFIG_PATH, LOGGER)
        set_logger_level(LOGGER, self.store.get().config.log_level)

    @staticmethod
    def _request_host(flow: http.HTTPFlow) -> str:
        return flow.request.pretty_host or flow.request.host or ""

    @staticmethod
    def _request_path(flow: http.HTTPFlow) -> str:
        return flow.request.path.split("?", 1)[0]

    @staticmethod
    def _build_block_response(block: BlockResponse) -> http.Response:
        body = json.dumps(block.body).encode("utf-8")
        return http.Response.make(
            block.status,
            body,
            {
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "X-Doubleagent-Blocked": "true",
            },
        )

    def request(self, flow: http.HTTPFlow) -> None:
        loaded = self.store.get()
        set_logger_level(LOGGER, loaded.config.log_level)
        host = self._request_host(flow)
        path = self._request_path(flow)
        method = flow.request.method

        block = check_block(loaded, host, method, path)
        if block is not None:
            flow.response = self._build_block_response(block)
            return

        inject_request_secrets(
            loaded=loaded,
            hostname=host,
            headers=flow.request.headers,
            query=flow.request.query,
        )


addons = [DoubleAgentAddon()]
