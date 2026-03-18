# doubleagent

A proxy sidecar for AI containers that enforces network policy through topology-level isolation. It swaps placeholder secrets for real ones and blocks unsafe requests before they leave the stack.

## What it does

- The AI agent is placed on an internal Docker network with **no internet access**.
- `doubleagent` bridges between the isolated network and the internet, acting as the AI's only path out.
- The AI only sees placeholder keys in its own environment.
- `doubleagent` replaces placeholders in headers or query params with real secrets.
- `doubleagent` can block requests by method and path.
- `doubleagent` can forward TCP ports from the host to the agent, so you can access the agent's web UI without breaking network isolation.
- Even if the agent ignores `HTTP_PROXY`, opens raw sockets, or unsets env vars, it cannot reach the internet — the network topology itself is the enforcement layer.

## Security model

```
                    ┌──────────────────────┐
                    │     AI Agent         │
                    │  (no internet route) │
                    └──────────┬───────────┘
                               │ agent_net (internal, no gateway)
                    ┌──────────┴───────────┐
                    │    doubleagent       │
                    │  policy + secrets    │
                    └──────────┬───────────┘
                               │ default bridge (internet access)
                    ┌──────────┴───────────┐
                    │      Internet        │
                    └──────────────────────┘
```

The AI container is connected **only** to `agent_net`, an `internal: true` Docker network. Docker does not create a gateway or NAT rules for internal networks, so there is no route to the outside world. The only service reachable by the AI is `doubleagent`, which inspects, filters, and forwards allowed requests.

This is fundamentally stronger than relying on `HTTP_PROXY` alone, because enforcement is mandatory regardless of agent behavior.

## Quick start

**1. Create a config file**

Start from `config/config.example.json` and trim it down for your use case, or create a minimal file like this:

```json
{
  "rules": [
    {
      "domains": ["api.openai.com"],
      "secrets": [
        {
          "placeholder": "PLACEHOLDER_OPENAI_KEY",
          "value_from_env": "OPENAI_API_KEY",
          "inject_in": ["header:Authorization"]
        }
      ],
      "rules": [
        {
          "policy": "block",
          "method": "DELETE",
          "path_pattern": "/v1/files/*",
          "response": {
            "status": 403,
            "body": {"error": "blocked by doubleagent"}
          }
        }
      ]
    }
  ],
  "default_policy": "allow"
}
```

**2. Add the sidecar to Compose**

```yaml
services:
  doubleagent:
    build: .
    networks:
      - default      # internet access
      - agent_net    # receives traffic from the AI
    volumes:
      - certs:/certs
      - ./config.json:/config/config.json:ro
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}

  ai-agent:
    image: your-ai-agent:latest
    networks:
      - agent_net    # NO internet access — only route is through doubleagent
    depends_on:
      doubleagent:
        condition: service_healthy
    volumes:
      - certs:/certs:ro
    environment:
      - OPENAI_API_KEY=Bearer PLACEHOLDER_OPENAI_KEY
      - HTTP_PROXY=http://doubleagent:8080
      - HTTPS_PROXY=http://doubleagent:8080
      - NODE_EXTRA_CA_CERTS=/certs/ca.crt
      - REQUESTS_CA_BUNDLE=/certs/ca.crt
      - SSL_CERT_FILE=/certs/ca.crt

networks:
  default:
    driver: bridge
  agent_net:
    driver: bridge
    internal: true    # no gateway, no NAT — this is what makes it secure

volumes:
  certs:
```

**3. Run it**

```bash
docker compose up
```

The proxy exposes `GET /healthz` and `GET /readyz` on port `9000` by default.

## Development

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Or use:

```bash
make install
make test
```

Run locally:

```bash
PYTHONPATH=. python -m doubleagent.main --config /config/config.json
```

## Config reference

If you want editor autocomplete and validation for a root-level `config.json`, add this as the first property in the file:

```json
{
  "$schema": "./config/config.schema.json",
  "...": "rest of your config"
}
```

Secret injection supports:

- `header:Name` - replace a placeholder in a header value
- `query:param` - replace a placeholder in a query parameter

Secrets can use `value` or `value_from_env`. If you need fixed text around the placeholder, include it in the original value, for example `Bearer PLACEHOLDER_OPENAI_KEY`.

Request `rules` match HTTP method and glob path pattern. Matching `policy: "allow"` rules override matching `policy: "block"` rules for the same domain.

Set `policy: "allow"` to allow every request for matching domains, or `policy: "block"` to block every request for matching domains.

`doubleagent` reloads the config file automatically when it changes. If a reload fails, it keeps serving the last valid configuration.

`default_policy` is `allow` or `block`.

## Port forwarding

Since the AI agent is on an internal Docker network, it cannot publish ports to the host. To access agent services (e.g. a web UI), configure `doubleagent` to forward TCP ports:

```json
{
  "forward_ports": [
    {
      "listen_port": 3000,
      "target_host": "ai-agent",
      "target_port": 3000
    }
  ]
}
```

Then publish the port on the `doubleagent` container in your compose file:

```yaml
services:
  doubleagent:
    ports:
      - "3000:3000"
```

Traffic flows: `host:3000 → doubleagent:3000 → ai-agent:3000` over the internal network. The agent remains fully isolated — this is a TCP relay, not an escape route.
