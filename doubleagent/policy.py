from __future__ import annotations

from collections.abc import MutableMapping

from doubleagent.config import (
    AllowRule,
    BlockResponse,
    BlockRule,
    LoadedConfig,
    ResolvedSecret,
    match_domain,
    match_path,
)


HEADER_PREFIX = "header:"
QUERY_PREFIX = "query:"


def _method_matches(request_method: str, rule_method: str | None) -> bool:
    return rule_method is None or rule_method.upper() == request_method.upper()


def _matches_allow_rule(method: str, path: str, allow_rules: list[AllowRule]) -> bool:
    for allow in allow_rules:
        method_match = _method_matches(method, allow.method)
        path_match = not allow.path_pattern or match_path(path, allow.path_pattern)
        if method_match and path_match:
            return True
    return False


def _matches_block_rule(method: str, path: str, block_rules: list[BlockRule]) -> BlockResponse | None:
    for block in block_rules:
        method_match = _method_matches(method, block.method)
        path_match = match_path(path, block.path_pattern)
        if method_match and path_match:
            return block.response
    return None


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

        if rule.policy == "allow":
            return None

        if rule.policy == "block":
            matched_block = BlockResponse(
                status=403,
                body={"error": "blocked", "reason": "domain is blocked by doubleagent policy"},
            )
            continue

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
    for rule_index, rule in enumerate(loaded.config.rules):
        if match_domain(hostname, rule.domains):
            result.extend(loaded.resolved_secrets.get(rule_index, []))
    return result


def _get_header(headers: MutableMapping[str, str], name: str) -> tuple[str | None, str | None]:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return key, value
    return None, None


def _inject_secret_at_location(
    secret: ResolvedSecret,
    location: str,
    headers: MutableMapping[str, str],
    query: MutableMapping[str, str],
) -> None:
    if location.startswith(HEADER_PREFIX):
        header_name = location.removeprefix(HEADER_PREFIX)
        actual_key, current_value = _get_header(headers, header_name)
        if actual_key and current_value and secret.placeholder in current_value:
            headers[actual_key] = current_value.replace(secret.placeholder, secret.resolved_value)
        return

    if location.startswith(QUERY_PREFIX):
        query_name = location.removeprefix(QUERY_PREFIX)
        current_value = query.get(query_name)
        if current_value and secret.placeholder in current_value:
            query[query_name] = current_value.replace(secret.placeholder, secret.resolved_value)


def inject_request_secrets(
    loaded: LoadedConfig,
    hostname: str,
    headers: MutableMapping[str, str],
    query: MutableMapping[str, str],
) -> None:
    secrets = resolve_secrets_for_host(loaded, hostname)
    if not secrets:
        return

    for secret in secrets:
        for location in secret.inject_in:
            _inject_secret_at_location(secret, location, headers, query)
