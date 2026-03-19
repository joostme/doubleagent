from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass

from doubleagent.config import (
    BlockResponse,
    LoadedConfig,
    RequestRule,
    ResolvedSecret,
    match_domain,
    match_path,
)


HEADER_PREFIX = "header:"
QUERY_PREFIX = "query:"


@dataclass(frozen=True)
class PolicyDecision:
    policy: str
    block_response: BlockResponse | None = None


def _method_matches(request_method: str, rule_method: str | None) -> bool:
    return rule_method is None or rule_method.upper() == request_method.upper()


def _match_request_rule(method: str, path: str, request_rule: RequestRule) -> bool:
    method_match = _method_matches(method, request_rule.method)
    path_match = not request_rule.path_pattern or match_path(path, request_rule.path_pattern)
    return method_match and path_match


def resolve_policy(
    loaded: LoadedConfig,
    hostname: str,
    method: str,
    path: str,
) -> PolicyDecision:
    matched_domain = False

    for rule in loaded.config.rules:
        if not match_domain(hostname, rule.domains):
            continue
        matched_domain = True

        matched_request_block: BlockResponse | None = None
        for request_rule in rule.rules:
            if not _match_request_rule(method, path, request_rule):
                continue
            if request_rule.policy == "allow":
                return PolicyDecision(policy="allow")
            if request_rule.response is not None:
                matched_request_block = request_rule.response

        if matched_request_block is not None:
            return PolicyDecision(policy="block", block_response=matched_request_block)

        if rule.policy == "allow":
            return PolicyDecision(policy="allow")

        if rule.policy == "bypass":
            return PolicyDecision(policy="bypass")

        if rule.policy == "block":
            return PolicyDecision(
                policy="block",
                block_response=BlockResponse(
                    status=403,
                    body={"error": "blocked", "reason": "domain is blocked by doubleagent policy"},
                ),
            )

    if loaded.config.default_policy == "block":
        reason = (
            "request is not explicitly allowed and default policy is block"
            if matched_domain
            else "no matching rule and default policy is block"
        )
        return PolicyDecision(
            policy="block",
            block_response=BlockResponse(status=403, body={"error": "blocked", "reason": reason}),
        )

    return PolicyDecision(policy="allow")


def check_block(
    loaded: LoadedConfig,
    hostname: str,
    method: str,
    path: str,
) -> BlockResponse | None:
    decision = resolve_policy(loaded, hostname, method, path)
    return decision.block_response


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
