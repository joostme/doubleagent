from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


def _is_valid_inject_location(value: str) -> bool:
    if value == "body":
        return True
    parts = value.split(":")
    if len(parts) < 2:
        return False
    kind, *rest = parts
    return kind in {"header", "query"} and bool(":".join(rest))


class BlockResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: int = Field(ge=100, le=599)
    body: dict[str, Any]


class SecretRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    placeholder: str = Field(min_length=1)
    value: str | None = None
    value_from_env: str | None = None
    inject_in: list[str] = Field(min_length=1)
    prefix: str = ""

    @field_validator("inject_in")
    @classmethod
    def validate_inject_in(cls, value: list[str]) -> list[str]:
        if not all(_is_valid_inject_location(item) for item in value):
            raise ValueError(
                "inject_in entries must be 'body', 'header:<name>', or 'query:<name>'"
            )
        return value


class BlockRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str | None = None
    path_pattern: str = Field(min_length=1)
    response: BlockResponse


class AllowRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str | None = None
    path_pattern: str | None = None


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domains: list[str] = Field(min_length=1)
    secrets: list[SecretRule] = Field(default_factory=list)
    block: bool | list[BlockRule] = Field(default_factory=list)
    allow: bool | list[AllowRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_allow_block(self) -> Rule:
        if self.allow is True and self.block is True:
            raise ValueError("rule cannot set both allow and block to true")
        return self


class CAConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cert_path: str = "/certs/ca.crt"


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    log_level: str = "info"
    ca: CAConfig = Field(default_factory=CAConfig)
    rules: list[Rule] = Field(default_factory=list)
    default_policy: str = "allow"
    http_port: int = 8080
    health_port: int = 9000
    proxy_uid: int = 1000
    allow_http_secret_injection: bool = False

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        if value not in {"debug", "info", "warning", "error"}:
            raise ValueError("log_level must be one of debug, info, warning, error")
        return value

    @field_validator("default_policy")
    @classmethod
    def validate_default_policy(cls, value: str) -> str:
        if value not in {"allow", "deny"}:
            raise ValueError("default_policy must be allow or deny")
        return value


@dataclass(frozen=True)
class ResolvedSecret:
    placeholder: str
    resolved_value: str
    inject_in: tuple[str, ...]
    prefix: str


@dataclass(frozen=True)
class LoadedConfig:
    config: Config
    resolved_secrets: dict[int, list[ResolvedSecret]]


def load_config(path: str | os.PathLike[str]) -> Config:
    data = Path(path).read_bytes()
    return Config.model_validate_json(data)


def resolve_secrets(config: Config) -> dict[int, list[ResolvedSecret]]:
    result: dict[int, list[ResolvedSecret]] = {}
    for i, rule in enumerate(config.rules):
        secrets: list[ResolvedSecret] = []
        for secret in rule.secrets:
            value = secret.value or ""
            if secret.value_from_env:
                value = os.environ.get(secret.value_from_env, "")
                if not value:
                    raise RuntimeError(
                        f'rule {i}: env var "{secret.value_from_env}" is not set'
                    )
            secrets.append(
                ResolvedSecret(
                    placeholder=secret.placeholder,
                    resolved_value=value,
                    inject_in=tuple(secret.inject_in),
                    prefix=secret.prefix,
                )
            )
        if secrets:
            result[i] = secrets
    return result


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


def match_domain(hostname: str, patterns: list[str]) -> bool:
    host = _strip_host_port(hostname)
    for pattern in patterns:
        current = _strip_host_port(pattern)
        if current == host:
            return True
        if current.startswith("*."):
            suffix = current[1:]
            if host.endswith(suffix) and host.count(".") >= suffix.count("."):
                return True
    return False


def match_path(path: str, pattern: str) -> bool:
    path_parts = [part for part in path.strip("/").split("/") if part]
    pattern_parts = [part for part in pattern.strip("/").split("/") if part]

    def _match(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)

        token = pattern_parts[pattern_index]
        if token == "**":
            if pattern_index == len(pattern_parts) - 1:
                return True
            for next_path_index in range(path_index, len(path_parts) + 1):
                if _match(next_path_index, pattern_index + 1):
                    return True
            return False

        if path_index >= len(path_parts):
            return False

        if token == "*" or token == path_parts[path_index]:
            return _match(path_index + 1, pattern_index + 1)

        return False

    return _match(0, 0)


class ConfigStore:
    def __init__(self, path: str | os.PathLike[str], logger: logging.Logger | None = None):
        self.path = Path(path)
        self.logger = logger or logging.getLogger(__name__)
        self._lock = RLock()
        self._mtime_ns: int | None = None
        self._loaded = self._load_current()

    def get(self) -> LoadedConfig:
        with self._lock:
            self._reload_if_needed()
            return self._loaded

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
            self._loaded = self._load_current()
        except (ValidationError, RuntimeError, ValueError) as exc:
            self.logger.error("failed to reload config, keeping previous version: %s", exc)
        else:
            self.logger.info("config reloaded successfully")
