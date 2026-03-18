from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

from doubleagent.ca import export_generated_ca, prepare_confdir
from doubleagent.config import DEFAULT_CONFIG_PATH, Config, load_config, resolve_secrets
from doubleagent.forward import ForwardTarget, PortForwarder
from doubleagent.health import HealthServer
from doubleagent.logging_utils import resolve_log_level


APP_PYTHONPATH = "/app"


def create_logger(level: str) -> logging.Logger:
    numeric_level = resolve_log_level(level)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger("doubleagent")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Explicit proxy sidecar for AI containers")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="path to config file")
    return parser.parse_args()


def build_mitmdump_command(listen_port: int, confdir: str | Path) -> list[str]:
    addon_path = Path(__file__).with_name("addon.py")
    return [
        "mitmdump",
        "--mode",
        "regular",
        "--showhost",
        "--listen-host",
        "0.0.0.0",
        "--listen-port",
        str(listen_port),
        "-s",
        str(addon_path),
        "--set",
        f"confdir={confdir}",
        "--set",
        "block_global=false",
    ]


def build_proxy_environment(config_path: str) -> dict[str, str]:
    env = os.environ.copy()
    env["DOUBLEAGENT_CONFIG"] = config_path

    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = APP_PYTHONPATH if not existing_pythonpath else f"{APP_PYTHONPATH}:{existing_pythonpath}"
    return env


def _terminate_child_process(child: subprocess.Popen[bytes] | subprocess.Popen[str], logger: logging.Logger) -> None:
    try:
        child.terminate()
    except ProcessLookupError:
        return
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("mitmdump did not exit cleanly, killing it")
        child.kill()
        child.wait()


def _log_startup(config_path: str, config: Config, logger: logging.Logger) -> None:
    logger.info(
        "doubleagent starting",
        extra={
            "config": config_path,
            "log_level": config.log_level,
            "default_policy": config.default_policy,
            "rules": len(config.rules),
            "mode": "explicit-proxy",
        },
    )


def _export_ca_or_stop(
    child: subprocess.Popen[bytes] | subprocess.Popen[str],
    confdir: Path,
    cert_path: str,
    logger: logging.Logger,
) -> None:
    try:
        export_generated_ca(confdir, cert_path, logger)
    except Exception:
        _terminate_child_process(child, logger)
        raise


def _install_signal_handlers(
    child: subprocess.Popen[bytes] | subprocess.Popen[str],
    logger: logging.Logger,
) -> None:
    def _forward(signum: int, _frame: object | None) -> None:
        logger.info("received signal %s, forwarding to mitmdump", signum)
        try:
            child.send_signal(signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGINT, _forward)
    signal.signal(signal.SIGTERM, _forward)


def _build_forward_targets(config: Config) -> list[ForwardTarget]:
    return [
        ForwardTarget(
            listen_port=fp.listen_port,
            target_host=fp.target_host,
            target_port=fp.target_port,
        )
        for fp in config.forward_ports
    ]


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    logger = create_logger(config.log_level)

    _log_startup(args.config, config, logger)

    # Validate that all secret env vars are set before starting the proxy.
    # The actual resolved secrets are loaded per-request by ConfigStore in the addon.
    resolve_secrets(config)
    logger.info("all secrets resolved successfully")

    confdir = prepare_confdir(config.ca.cert_path, logger)
    ready = threading.Event()
    health_server = HealthServer(config.health_port, ready)
    health_server.start()

    forward_targets = _build_forward_targets(config)
    forwarder = PortForwarder(forward_targets, logger) if forward_targets else None

    env = build_proxy_environment(args.config)
    cmd = build_mitmdump_command(config.http_port, confdir)
    logger.info("starting mitmdump: %s", " ".join(cmd))

    child = subprocess.Popen(cmd, env=env)

    try:
        _export_ca_or_stop(child, confdir, config.ca.cert_path, logger)

        if forwarder:
            forwarder.start()

        ready.set()
        _install_signal_handlers(child, logger)

        return child.wait()
    finally:
        ready.clear()
        if forwarder:
            forwarder.stop()
        health_server.stop()


if __name__ == "__main__":
    sys.exit(main())
