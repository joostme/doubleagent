from __future__ import annotations

import logging


def resolve_log_level(level: str) -> int:
    return getattr(logging, level.upper(), logging.INFO)


def set_logger_level(logger: logging.Logger, level: str) -> None:
    logger.setLevel(resolve_log_level(level))
