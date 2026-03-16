# doubleagent

A transparent proxy sidecar that sits between your AI agent and the internet — injecting real API keys and blocking dangerous requests, without the agent ever knowing.

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────┐
│              │       │  doubleagent     │       │              │
│   AI Agent   │──────>│                  │──────>│   Internet   │
│              │       │  ✓ swap secrets  │       │              │
│  (only sees  │       │  ✗ block DELETE  │       │  api.openai  │
│  fake keys)  │       │  ✓ forward safe  │       │  github.com  │
│              │       │    requests      │       │  etc.        │
└──────────────┘       └──────────────────┘       └──────────────┘
    network_mode:           iptables
    service:doubleagent     REDIRECT
```

## Why

AI agents need API keys to work. But giving an agent real credentials means it can leak them, exfiltrate them, or use them to do things you didn't intend — like deleting your GitHub repos.

doubleagent solves this by acting as a **double agent**: it pretends to be a transparent network to the AI, while secretly working for you — swapping in real keys and enforcing your rules.

- **Secret injection** — The AI only sees placeholder keys. doubleagent swaps them for real credentials in-flight, in headers, query params, or request bodies.
- **Request blocking** — Block dangerous API calls by method and path pattern. `DELETE /repos/*/*`? Blocked. `POST /v1/chat/completions`? Allowed.
- **Transparent** — No proxy config needed. iptables + mitmproxy transparent mode capture all traffic automatically.
- **Hot-reload** — Update rules without restarting.

## Quick start

**1. Create a config file**

```json
{
  "rules": [
    {
      "domains": ["api.openai.com"],
      "secrets": [
        {
          "placeholder": "PLACEHOLDER_OPENAI_KEY",
          "value_from_env": "OPENAI_API_KEY",
          "inject_in": ["header:Authorization"],
          "prefix": "Bearer "
        }
      ],
      "block": [
        {
          "method": "DELETE",
          "path_pattern": "/v1/files/*",
          "response": {
            "status": 403,
            "body": { "error": "blocked by doubleagent" }
          }
        }
      ]
    }
  ],
  "default_policy": "allow"
}
```

**2. Add to your docker-compose.yml**

```yaml
services:
  doubleagent:
    build: .
    cap_add:
      - NET_ADMIN
    volumes:
      - certs:/certs
      - ./config.json:/config/config.json:ro
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}

  ai-agent:
    image: your-ai-agent:latest
    network_mode: "service:doubleagent"
    depends_on:
      doubleagent:
        condition: service_healthy
    volumes:
      - certs:/usr/local/share/ca-certificates/doubleagent:ro
    environment:
      - OPENAI_API_KEY=PLACEHOLDER_OPENAI_KEY
      - NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/doubleagent/ca.crt
    command: sh -c "update-ca-certificates 2>/dev/null; exec your-command"

volumes:
  certs:
```

**3. Run it**

```
docker compose up
```

The AI agent sees `PLACEHOLDER_OPENAI_KEY`. doubleagent replaces it with your real key on the wire. DELETE requests to `/v1/files/*` get a 403 back. The agent never knows.

## Development

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Or use the helper targets:

```bash
make install
make test
```

Run locally without touching iptables:

```bash
PYTHONPATH=. python -m doubleagent.main --skip-iptables --config /config/config.json
```

## How it works

doubleagent runs as a Docker sidecar that owns the network namespace. The AI container shares it via `network_mode: "service:doubleagent"`. All outbound HTTP/HTTPS traffic is captured by iptables NAT rules and redirected to a mitmproxy-powered transparent proxy, which terminates TLS with an auto-generated CA, inspects and modifies requests, then forwards them to the real destination.

Internally, mitmproxy transparent mode listens on a single intercept port. `doubleagent` keeps the historical `http_port` and `https_port` config fields for compatibility, but both protocols are redirected to the same mitmproxy listener.

The CA is owned by mitmproxy. `doubleagent` exports the generated CA certificate to `ca.cert_path` so the agent container can trust it, but it does not generate leaf certificates or manage a separate CA key anymore.

## Config reference

**Secret injection** supports three locations:

| Location | Example | What it does |
|----------|---------|--------------|
| `header:Name` | `header:Authorization` | Replace placeholder in the named header |
| `query:param` | `query:api_key` | Replace placeholder in a query parameter |
| `body` | `body` | Replace placeholder anywhere in the request body |

Secrets can be set as a static `value` or loaded from environment variables with `value_from_env`. An optional `prefix` is prepended to the resolved value before injection — useful for `Authorization: Bearer <token>` patterns.

**Block rules** match by HTTP method and glob path pattern (`*` for single segment, `**` for multiple). Allow rules take priority over blocks.

**Default policy** is `allow` (forward unmatched traffic) or `deny` (block everything without an explicit rule).

**Plain HTTP injection** is disabled by default. Set `allow_http_secret_injection: true` only for trusted plaintext upstreams such as localhost-only services.
