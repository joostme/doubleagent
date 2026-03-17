from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path


def prepare_confdir(cert_path: str, logger: logging.Logger) -> Path:
    cert_file = Path(cert_path)
    cert_file.parent.mkdir(parents=True, exist_ok=True)
    logger.info("using mitmproxy-managed CA in confdir %s", cert_file.parent)
    return cert_file.parent


def export_generated_ca(
    confdir: Path,
    cert_path: str,
    logger: logging.Logger,
    timeout_seconds: float = 10.0,
) -> Path:
    cert_file = Path(cert_path)
    source = confdir / "mitmproxy-ca-cert.pem"
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if source.exists():
            cert_file.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() != cert_file.resolve():
                shutil.copyfile(source, cert_file)
            logger.info("exported mitmproxy CA certificate to %s", cert_file)
            return cert_file
        time.sleep(0.1)

    raise TimeoutError(
        f"mitmproxy did not generate {source.name} within {timeout_seconds} seconds"
    )
