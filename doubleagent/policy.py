from __future__ import annotations

import logging
from collections.abc import MutableMapping

from doubleagent.config import BlockResponse, LoadedConfig, ResolvedSecret, match_domain, match_path


def _matches_allow_rule(method: str, path: str, allow_rules: bool | list) -> bool:
    if allow_rules is True:
        return True
    if allow_rules is False:
        return False

    for allow in allow_rules:
        method_match = not allow.method or allow.method.upper() == method.upper()
        path_match = not allow.path_pattern or match_path(path, allow.path_pattern)
        if method_match and path_match:
            return True
    return False


def _matches_block_rule(method: str, path: str, block_rules: bool | list) -> BlockResponse | None:
    if block_rules is True:
        return BlockResponse(
            status=403,
            body={"error": "blocked", "reason": "domain is blocked by doubleagent policy"},
        )
    if block_rules is False:
        return None

    matched_block: BlockResponse | None = None
    for block in block_rules:
        method_match = not block.method or block.method.upper() == method.upper()
        path_match = match_path(path, block.path_pattern)
        if method_match and path_match:
            matched_block = block.response
    return matched_block


def check_block(
    loaded: LoadedConfig,
    hostname: str,
    method: str,
    path: str,
) -> BlockResponse | None:
    matched_domain = False
    matched_block: BlockResponse | None = None

    for rule in loaded.config.rules:
        if not match_domain(hostname, rule.domains):
            continue
        matched_domain = True

        if _matches_allow_rule(method, path, rule.allow):
            return None

        block = _matches_block_rule(method, path, rule.block)
        if block is not None:
            matched_block = block

    if matched_block:
        return matched_block

    if loaded.config.default_policy == "block":
        reason = (
            "request is not explicitly allowed and default policy is block"
            if matched_domain
            else "no matching rule and default policy is block"
        )
        return BlockResponse(status=403, body={"error": "blocked", "reason": reason})

    return None


def resolve_secrets_for_host(loaded: LoadedConfig, hostname: str) -> list[ResolvedSecret]:
    result: list[ResolvedSecret] = []
    for i, rule in enumerate(loaded.config.rules):
        if match_domain(hostname, rule.domains):
            result.extend(loaded.resolved_secrets.get(i, []))
    return result


def _get_header(headers: MutableMapping[str, str], name: str) -> tuple[str | None, str | None]:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return key, value
    return None, None


def _set_query_value(query: MutableMapping[str, str], name: str, value: str) -> None:
    query[name] = value


def inject_request_secrets(
    loaded: LoadedConfig,
    hostname: str,
    scheme: str,
    headers: MutableMapping[str, str],
    query: MutableMapping[str, str],
    logger: logging.Logger,
) -> None:
    secrets = resolve_secrets_for_host(loaded, hostname)
    if not secrets:
        return

    if scheme.lower() != "https" and not loaded.config.allow_http_secret_injection:
        logger.warning(
            "refusing to inject secrets into plaintext HTTP request for host %s",
            hostname,
        )
        return

    for secret in secrets:
        full_value = f"{secret.prefix}{secret.resolved_value}"
        for location in secret.inject_in:
            if location.startswith("header:"):
                header_name = location[len("header:") :]
                actual_key, current_value = _get_header(headers, header_name)
                if actual_key and current_value and secret.placeholder in current_value:
                    headers[actual_key] = current_value.replace(secret.placeholder, full_value)
            elif location.startswith("query:"):
                query_name = location[len("query:") :]
                current_value = query.get(query_name)
                if current_value and secret.placeholder in current_value:
                    _set_query_value(
                        query,
                        query_name,
                        current_value.replace(secret.placeholder, full_value),
                    )
