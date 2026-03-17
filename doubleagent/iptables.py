from __future__ import annotations

import logging
import subprocess
from pathlib import Path


OUTPUT_CHAIN_V4 = "DOUBLEAGENT_OUTPUT"
OUTPUT_CHAIN_V6 = "DOUBLEAGENT_OUTPUT_V6"

def _parse_cgroup_v2_path(contents: str) -> str | None:
    for line in contents.splitlines():
        hierarchy, separator, remainder = line.partition(":")
        if separator != ":":
            continue
        controllers, separator, path = remainder.partition(":")
        if separator != ":":
            continue
        if hierarchy == "0" and controllers == "":
            return path or "/"
    return None


def get_process_cgroup_path(proc_cgroup_path: str | Path = "/proc/self/cgroup") -> str:
    contents = Path(proc_cgroup_path).read_text(encoding="utf-8")
    cgroup_path = _parse_cgroup_v2_path(contents)
    if cgroup_path is None:
        raise RuntimeError(
            "unable to determine proxy cgroup path from cgroup v2; refusing to install insecure UID-based bypass"
        )
    if cgroup_path == "/":
        raise RuntimeError("proxy process is running in the root cgroup; refusing to bypass all traffic")
    return cgroup_path


def _run(binary: str, args: list[str], logger: logging.Logger) -> None:
    try:
        subprocess.run([binary, *args], check=True, capture_output=True, text=True)
        logger.debug("applied rule: %s %s", binary, " ".join(args))
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else str(exc)
        raise RuntimeError(f"{binary} {' '.join(args)}: {stderr}") from exc


def _is_missing_rule(exc: Exception) -> bool:
    msg = str(exc)
    return "Bad rule" in msg or "No chain/target/match by that name" in msg


def _is_missing_chain(exc: Exception) -> bool:
    return "No chain/target/match by that name" in str(exc)


def _create_chain(binary: str, name: str, logger: logging.Logger) -> None:
    try:
        _run(binary, ["-t", "nat", "-N", name], logger)
    except RuntimeError as exc:
        if "Chain already exists" not in str(exc):
            raise


def _flush_chain(binary: str, name: str, logger: logging.Logger) -> None:
    _run(binary, ["-t", "nat", "-F", name], logger)


def _delete_chain(binary: str, name: str, logger: logging.Logger) -> None:
    _run(binary, ["-t", "nat", "-X", name], logger)


def _delete_jump(binary: str, parent: str, child: str, logger: logging.Logger) -> None:
    args = ["-t", "nat", "-D", parent, "-j", child]
    while True:
        try:
            _run(binary, args, logger)
        except RuntimeError as exc:
            if _is_missing_rule(exc):
                return
            raise


def _ensure_jump(binary: str, parent: str, child: str, logger: logging.Logger) -> None:
    _delete_jump(binary, parent, child, logger)
    _run(binary, ["-t", "nat", "-I", parent, "1", "-j", child], logger)


def _setup_family(
    binary: str,
    output_chain: str,
    intercept_port: int,
    proxy_cgroup_path: str,
    logger: logging.Logger,
) -> None:
    _create_chain(binary, output_chain, logger)
    _flush_chain(binary, output_chain, logger)

    output_rules = [
        ["-t", "nat", "-A", output_chain, "-m", "cgroup", "--path", proxy_cgroup_path, "-j", "RETURN"],
        ["-t", "nat", "-A", output_chain, "-o", "lo", "-j", "RETURN"],
        ["-t", "nat", "-A", output_chain, "-p", "tcp", "--dport", "80", "-j", "REDIRECT", "--to-ports", str(intercept_port)],
        ["-t", "nat", "-A", output_chain, "-p", "tcp", "--dport", "443", "-j", "REDIRECT", "--to-ports", str(intercept_port)],
        ["-t", "nat", "-A", output_chain, "-p", "tcp", "-j", "REDIRECT", "--to-ports", str(intercept_port)],
    ]

    for args in output_rules:
        _run(binary, args, logger)

    _ensure_jump(binary, "OUTPUT", output_chain, logger)


def setup(intercept_port: int, proxy_cgroup_path: str, logger: logging.Logger) -> None:
    logger.info(
        "setting up iptables rules",
        extra={"intercept_port": intercept_port, "proxy_cgroup_path": proxy_cgroup_path},
    )
    cleanup(logger, log_missing=False)
    _setup_family("iptables", OUTPUT_CHAIN_V4, intercept_port, proxy_cgroup_path, logger)
    try:
        _setup_family("ip6tables", OUTPUT_CHAIN_V6, intercept_port, proxy_cgroup_path, logger)
    except RuntimeError as exc:
        logger.warning("failed to set up ip6tables rules: %s", exc)
    logger.info("iptables rules installed successfully")


def _cleanup_family(binary: str, output_chain: str, logger: logging.Logger, errors: list[str]) -> None:
    try:
        _delete_jump(binary, "OUTPUT", output_chain, logger)
    except RuntimeError as exc:
        errors.append(str(exc))

    try:
        _flush_chain(binary, output_chain, logger)
    except RuntimeError as exc:
        if not _is_missing_chain(exc):
            errors.append(str(exc))
    try:
        _delete_chain(binary, output_chain, logger)
    except RuntimeError as exc:
        if not _is_missing_chain(exc):
            errors.append(str(exc))


def cleanup(logger: logging.Logger, log_missing: bool = True) -> None:
    logger.info("cleaning up iptables rules")
    errors: list[str] = []
    _cleanup_family("iptables", OUTPUT_CHAIN_V4, logger, errors)
    try:
        _cleanup_family("ip6tables", OUTPUT_CHAIN_V6, logger, errors)
    except RuntimeError as exc:
        errors.append(str(exc))

    logger.info("iptables cleanup complete")
    if errors and log_missing:
        logger.warning("iptables cleanup had errors: %s", errors)
