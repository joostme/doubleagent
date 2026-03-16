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
from doubleagent.iptables import cleanup as cleanup_iptables
from doubleagent.iptables import get_process_cgroup_path
from doubleagent.iptables import setup as setup_iptables
from doubleagent.logging_utils import resolve_log_level


def create_logger(level: str) -> logging.Logger:
    numeric_level = resolve_log_level(level)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger("doubleagent")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transparent intercepting proxy sidecar for AI containers")
    parser.add_argument("--config", default="/config/config.json", help="path to config file")
    parser.add_argument("--skip-iptables", action="store_true", help="skip iptables setup (for testing)")
    parser.add_argument("--cleanup-iptables", action="store_true", help="remove managed iptables rules and exit")
    return parser.parse_args()


def _drop_privileges_preexec(uid: int):
    def _inner() -> None:
        if os.geteuid() != 0:
            return
        if uid == 0:
            raise RuntimeError("proxy_uid must not be 0 when running as root")
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
        if os.geteuid() != uid:
            raise RuntimeError(f"failed to drop privileges to uid {uid}")

    return _inner


def build_mitmdump_command(listen_port: int, confdir: Path) -> list[str]:
    addon_path = Path(__file__).with_name("addon.py")
    return [
        "mitmdump",
        "--mode",
        "transparent",
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
        },
    )

    if args.cleanup_iptables:
        if args.skip_iptables:
            logger.warning("skipping iptables cleanup (test mode)")
            return 0
        cleanup_iptables(logger)
        return 0

    resolve_secrets(config)
    logger.info("all secrets resolved successfully")

    if config.http_port != config.https_port:
        logger.warning(
            "mitmproxy transparent mode uses a single listen port; redirecting all traffic to http_port=%s (ignoring https_port=%s)",
            config.http_port,
            config.https_port,
        )

    confdir = prepare_confdir(config.ca.cert_path, logger)
    ready = threading.Event()
    health_server = HealthServer(config.health_port, ready)
    health_server.start()

    if not args.skip_iptables:
        proxy_cgroup_path = get_process_cgroup_path()
        logger.info("using proxy cgroup path for bypass matching: %s", proxy_cgroup_path)
        setup_iptables(config.http_port, proxy_cgroup_path, logger)
    else:
        logger.warning("skipping iptables setup (test mode)")

    env = os.environ.copy()
    env["DOUBLEAGENT_CONFIG"] = args.config
    env["PYTHONPATH"] = f"/app:{env.get('PYTHONPATH', '')}".rstrip(":")
    cmd = build_mitmdump_command(config.http_port, confdir)
    logger.info("starting mitmdump: %s", " ".join(cmd))

    child = subprocess.Popen(
        cmd,
        env=env,
        preexec_fn=_drop_privileges_preexec(config.proxy_uid),
    )
    export_generated_ca(confdir, config.ca.cert_path, logger)
    ready.set()

    def _forward(signum: int, _frame) -> None:
        logger.info("received signal %s, forwarding to mitmdump", signum)
        try:
            child.send_signal(signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGINT, _forward)
    signal.signal(signal.SIGTERM, _forward)

    try:
        return child.wait()
    finally:
        ready.clear()
        health_server.stop()
        if not args.skip_iptables:
            try:
                cleanup_iptables(logger)
            except Exception as exc:  # pragma: no cover
                logger.warning("iptables cleanup failed: %s", exc)


if __name__ == "__main__":
    sys.exit(main())
