from __future__ import annotations

import glob
import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


DEFAULT_CONFIG_PATH = "/config/config.json"


class StrictBaseModel(BaseModel):
    """Base model that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


def _is_valid_inject_location(value: str) -> bool:
    parts = value.split(":")
    if len(parts) < 2:
        return False
    kind, *rest = parts
    return kind in {"header", "query"} and bool(":".join(rest))


class BlockResponse(StrictBaseModel):
    status: int = Field(ge=100, le=599)
    body: dict[str, Any]


class SecretRule(StrictBaseModel):
    placeholder: str = Field(min_length=1)
    value: str | None = None
    value_from_env: str | None = None
    inject_in: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_secret_source(self) -> SecretRule:
        if self.value is not None and self.value_from_env is not None:
            raise ValueError("secret must set either 'value' or 'value_from_env', not both")
        return self

    @field_validator("inject_in")
    @classmethod
    def validate_inject_in(cls, value: list[str]) -> list[str]:
        if not all(_is_valid_inject_location(item) for item in value):
            raise ValueError("inject_in entries must be 'header:<name>' or 'query:<name>'")
        return value


class BlockRule(StrictBaseModel):
    method: str | None = None
    path_pattern: str = Field(min_length=1)
    response: BlockResponse


class AllowRule(StrictBaseModel):
    method: str | None = None
    path_pattern: str | None = None


class Rule(StrictBaseModel):
    domains: list[str] = Field(min_length=1)
    secrets: list[SecretRule] = Field(default_factory=list)
    block: bool | list[BlockRule] = Field(default_factory=list)
    allow: bool | list[AllowRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_allow_block(self) -> Rule:
        if self.allow is True and self.block is True:
            raise ValueError("rule cannot set both allow and block to true")
        return self


class ForwardPortRule(StrictBaseModel):
    listen_port: int = Field(ge=1, le=65535)
    target_host: str = Field(min_length=1)
    target_port: int = Field(ge=1, le=65535)


class CAConfig(StrictBaseModel):
    cert_path: str = "/certs/ca.crt"


class Config(StrictBaseModel):
    log_level: str = "info"
    ca: CAConfig = Field(default_factory=CAConfig)
    rules: list[Rule] = Field(default_factory=list)
    forward_ports: list[ForwardPortRule] = Field(default_factory=list)
    default_policy: str = "allow"
    http_port: int = 8080
    health_port: int = 9000

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        if value not in {"debug", "info", "warning", "error"}:
            raise ValueError("log_level must be one of debug, info, warning, error")
        return value

    @field_validator("default_policy")
    @classmethod
    def validate_default_policy(cls, value: str) -> str:
        if value not in {"allow", "block"}:
            raise ValueError("default_policy must be allow or block")
        return value


@dataclass(frozen=True)
class ResolvedSecret:
    placeholder: str
    resolved_value: str
    inject_in: tuple[str, ...]


@dataclass(frozen=True)
class LoadedConfig:
    config: Config
    resolved_secrets: dict[int, list[ResolvedSecret]]


def load_config(path: str | os.PathLike[str]) -> Config:
    data = Path(path).read_bytes()
    return Config.model_validate_json(data)


def _resolve_secret_value(secret: SecretRule, rule_index: int) -> str:
    if secret.value_from_env is None:
        return secret.value or ""

    value = os.environ.get(secret.value_from_env, "")
    if not value:
        raise RuntimeError(f'rule {rule_index}: env var "{secret.value_from_env}" is not set')
    return value


def resolve_secrets(config: Config) -> dict[int, list[ResolvedSecret]]:
    resolved_by_rule: dict[int, list[ResolvedSecret]] = {}
    for rule_index, rule in enumerate(config.rules):
        resolved_secrets: list[ResolvedSecret] = []
        for secret in rule.secrets:
            resolved_secrets.append(
                ResolvedSecret(
                    placeholder=secret.placeholder,
                    resolved_value=_resolve_secret_value(secret, rule_index),
                    inject_in=tuple(secret.inject_in),
                )
            )
        if resolved_secrets:
            resolved_by_rule[rule_index] = resolved_secrets
    return resolved_by_rule


def _strip_host_port(hostname: str) -> str:
    hostname = hostname.strip()
    if hostname.startswith("["):
        end = hostname.find("]")
        if end != -1:
            return hostname[1:end].lower()
    if hostname.count(":") == 1 and not hostname.endswith(":"):
        host, _sep, port = hostname.rpartition(":")
        if port.isdigit():
            return host.lower()
    return hostname.lower()


def _normalize_domain_pattern(pattern: str) -> str:
    current = _strip_host_port(pattern)
    if current.startswith("*."):
        return f".{current[2:]}"
    return current


def _match_single_domain(host: str, pattern: str) -> bool:
    """Match a hostname against a single normalized domain pattern.

    An exact match is required unless the pattern starts with '.',
    in which case any subdomain matches (but not the bare domain itself).
    For example, '.example.com' matches 'sub.example.com' but NOT 'example.com'.
    """
    if pattern.startswith("."):
        return host.endswith(pattern)
    return host == pattern


def match_domain(hostname: str, patterns: list[str]) -> bool:
    host = _strip_host_port(hostname)
    for pattern in patterns:
        current = _normalize_domain_pattern(pattern)
        if not current:
            continue
        if _match_single_domain(host, current):
            return True
    return False


@lru_cache(maxsize=256)
def _compile_path_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(glob.translate(pattern, recursive=True, include_hidden=True, seps="/"))


def match_path(path: str, pattern: str) -> bool:
    return bool(_compile_path_pattern(pattern).fullmatch(path))


class ConfigStore:
    def __init__(self, path: str | os.PathLike[str], logger: logging.Logger | None = None):
        self.path = Path(path)
        self.logger = logger or logging.getLogger(__name__)
        self._lock = RLock()
        self._mtime_ns: int | None = None
        self._current = self._load_current()

    def get(self) -> LoadedConfig:
        with self._lock:
            self._reload_if_needed()
            return self._current

    def _load_current(self) -> LoadedConfig:
        config = load_config(self.path)
        resolved = resolve_secrets(config)
        self._mtime_ns = self.path.stat().st_mtime_ns
        return LoadedConfig(config=config, resolved_secrets=resolved)

    def _reload_if_needed(self) -> None:
        try:
            mtime_ns = self.path.stat().st_mtime_ns
        except FileNotFoundError:
            self.logger.error("config file disappeared: %s", self.path)
            return

        if self._mtime_ns == mtime_ns:
            return

        self.logger.info("config file changed, reloading: %s", self.path)
        try:
            self._current = self._load_current()
        except (ValidationError, RuntimeError, ValueError) as exc:
            self.logger.error("failed to reload config, keeping previous version: %s", exc)
        else:
            self.logger.info("config reloaded successfully")
