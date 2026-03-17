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
from doubleagent.config import load_config, resolve_secrets
from doubleagent.health import HealthServer
from doubleagent.logging_utils import resolve_log_level


def create_logger(level: str) -> logging.Logger:
    numeric_level = resolve_log_level(level)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger("doubleagent")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Explicit proxy sidecar for AI containers")
    parser.add_argument("--config", default="/config/config.json", help="path to config file")
    return parser.parse_args()


def build_mitmdump_command(listen_port: int, confdir: Path) -> list[str]:
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


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    logger = create_logger(config.log_level)

    logger.info(
        "doubleagent starting",
        extra={
            "config": args.config,
            "log_level": config.log_level,
            "default_policy": config.default_policy,
            "rules": len(config.rules),
            "mode": "explicit-proxy",
        },
    )

    resolve_secrets(config)
    logger.info("all secrets resolved successfully")

    confdir = prepare_confdir(config.ca.cert_path, logger)
    ready = threading.Event()
    health_server = HealthServer(config.health_port, ready)
    health_server.start()

    env = os.environ.copy()
    env["DOUBLEAGENT_CONFIG"] = args.config
    env["PYTHONPATH"] = f"/app:{env.get('PYTHONPATH', '')}".rstrip(":")
    cmd = build_mitmdump_command(config.http_port, confdir)
    logger.info("starting mitmdump: %s", " ".join(cmd))

    child = subprocess.Popen(cmd, env=env)

    try:
        try:
            export_generated_ca(confdir, config.ca.cert_path, logger)
        except Exception:
            _terminate_child_process(child, logger)
            raise

        ready.set()

        def _forward(signum: int, _frame) -> None:
            logger.info("received signal %s, forwarding to mitmdump", signum)
            try:
                child.send_signal(signum)
            except ProcessLookupError:
                pass

        signal.signal(signal.SIGINT, _forward)
        signal.signal(signal.SIGTERM, _forward)

        return child.wait()
    finally:
        ready.clear()
        health_server.stop()


if __name__ == "__main__":
    sys.exit(main())
