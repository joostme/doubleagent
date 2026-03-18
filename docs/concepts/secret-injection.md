# Secret Injection

Secret injection is the mechanism by which `doubleagent` replaces placeholder
credentials in outbound requests with real API keys and tokens, without the
agent ever seeing the real values.

## The problem with giving agents real credentials

When an AI agent holds real API keys:

- A prompt injection could instruct the agent to exfiltrate credentials
- The agent could accidentally log or transmit secrets
- A compromised agent gives an attacker direct access to all connected services

## How doubleagent solves this

The agent only knows about **placeholder** values:

```yaml
# Agent container environment
OPENAI_API_KEY=PLACEHOLDER_OPENAI_KEY
GITHUB_TOKEN=PLACEHOLDER_GITHUB_TOKEN
```

The **real** credentials live exclusively on the `doubleagent` container:

```yaml
# doubleagent container environment
OPENAI_API_KEY=sk-real-key-here
GITHUB_TOKEN=ghp_real-token-here
```

When the agent sends a request with `Authorization: Bearer PLACEHOLDER_OPENAI_KEY`,
`doubleagent` intercepts it and replaces `PLACEHOLDER_OPENAI_KEY` with
`sk-real-key-here` before forwarding.

## What gets replaced

Secret injection is **targeted replacement**, not blind string substitution.
You specify exactly where each placeholder should be replaced:

- **Headers** -- `inject_in: ["header:Authorization"]` replaces the placeholder
  only in the `Authorization` header
- **Query parameters** -- `inject_in: ["query:api_key"]` replaces the placeholder
  only in the `api_key` query parameter

The replacement is a simple string substitution within the specified location.
If the header value is `Bearer PLACEHOLDER_OPENAI_KEY`, only the
`PLACEHOLDER_OPENAI_KEY` part is replaced -- the `Bearer ` prefix is preserved.

## Security properties

| Property | Description |
|---|---|
| Agent never sees real secrets | The agent process and its filesystem only contain placeholder values |
| Secrets stay in memory | Real secrets exist only in the `doubleagent` process memory and its environment variables |
| Targeted replacement | Secrets are only injected into explicitly configured locations (specific headers or query params) |
| Per-domain scoping | Each secret is associated with specific domains, preventing credential leakage to unrelated services |

## If the agent is compromised

Even if the agent is fully compromised by a prompt injection or other attack:

1. The attacker only sees placeholder values
2. Placeholder values are useless outside the `doubleagent` network
3. The attacker cannot extract real credentials from the agent's environment
4. The attacker still cannot bypass `doubleagent` due to
   [network isolation](network-isolation.md)

The attacker could still make *allowed* API calls through the proxy (using the
agent's existing access). This is where [rules](../configuration/rules.md) help --
blocking dangerous operations like `DELETE /repos/*/*` limits what a compromised
agent can do even through the proxy.
