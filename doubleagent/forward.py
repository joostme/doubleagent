"""TCP port forwarder for exposing AI agent services through doubleagent.

Since the AI agent container is on an internal-only Docker network, it cannot
publish ports to the host directly. This module lets doubleagent (which is on
both the internal and external networks) forward TCP connections from the host
to services running on the agent container.

Uses socat for the actual TCP relay — a battle-tested tool purpose-built for
bidirectional byte stream forwarding.

This is intentionally a dumb pipe — no TLS interception, no policy enforcement.
The traffic is inbound from the user to the agent, not outbound from the agent
to the internet, so it does not need inspection.
"""

from __future__ import annotations

import logging
import subprocess
from typing import NamedTuple

DEFAULT_LISTEN_HOST = "0.0.0.0"


class ForwardTarget(NamedTuple):
    listen_port: int
    target_host: str
    target_port: int


def _build_socat_command(
    target: ForwardTarget,
    listen_host: str = DEFAULT_LISTEN_HOST,
) -> list[str]:
    return [
        "socat",
        f"TCP-LISTEN:{target.listen_port},bind={listen_host},reuseaddr,fork",
        f"TCP:{target.target_host}:{target.target_port}",
    ]


class PortForwarder:
    """Manages socat processes for TCP port forwarding."""

    def __init__(self, targets: list[ForwardTarget], logger: logging.Logger | None = None):
        self._targets = targets
        self._logger = logger or logging.getLogger(__name__)
        self._processes: list[subprocess.Popen[bytes]] = []

    def start(self) -> None:
        for target in self._targets:
            cmd = _build_socat_command(target)
            self._logger.info("forward: %s", " ".join(cmd))
            proc = subprocess.Popen(cmd)
            self._processes.append(proc)

    def stop(self) -> None:
        for proc in self._processes:
            try:
                proc.terminate()
            except ProcessLookupError:
                continue
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._logger.warning("forward: socat pid %d did not exit cleanly, killing", proc.pid)
                proc.kill()
                proc.wait()
        self._processes.clear()
