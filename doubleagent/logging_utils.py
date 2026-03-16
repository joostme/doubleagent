from __future__ import annotations

import logging


def resolve_log_level(level: str) -> int:
    numeric_level = getattr(logging, level.upper(), None)
    if numeric_level is None:
        numeric_level = logging.INFO
    return numeric_level


def set_logger_level(logger: logging.Logger, level: str) -> None:
    logger.setLevel(resolve_log_level(level))
