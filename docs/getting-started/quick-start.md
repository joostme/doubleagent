# Quick Start

This guide walks you through adding `doubleagent` to an existing Docker Compose
stack. The examples assume you already have an `ai-agent` service.

## 1. Add `doubleagent` to your Compose file

This is the core of the setup. You are adding `doubleagent` as a sidecar,
creating an isolated network, and wiring your agent through it.

```yaml
services:
  # Your existing AI agent -- now on an isolated network
  ai-agent:
    image: my-ai-agent:latest
    networks:
      - agent_net                              # internal only, no internet
    depends_on:
      doubleagent:
        condition: service_healthy
    volumes:
      - certs:/certs:ro                        # trust the proxy CA + install-ca.sh
    # If your agent needs the CA in the system trust store (see Troubleshooting):
    # entrypoint: ["/bin/sh", "-c", "/certs/install-ca.sh && exec your-original-entrypoint"]
    environment:
      # Placeholders -- not real keys
      - OPENAI_API_KEY=PLACEHOLDER_OPENAI_KEY
      - GITHUB_TOKEN=PLACEHOLDER_GITHUB_TOKEN
      # Route traffic through doubleagent
      - HTTP_PROXY=http://doubleagent:8080
      - HTTPS_PROXY=http://doubleagent:8080
      - NO_PROXY=localhost,127.0.0.1,doubleagent
      # Trust the proxy CA certificate
      - NODE_EXTRA_CA_CERTS=/certs/ca.crt
      - REQUESTS_CA_BUNDLE=/certs/ca.crt
      - SSL_CERT_FILE=/certs/ca.crt
      - CURL_CA_BUNDLE=/certs/ca.crt
      - GIT_SSL_CAINFO=/certs/ca.crt

  # The security gateway
  doubleagent:
    build: .
    networks:
      - default                                # has internet access
      - agent_net                              # can talk to the agent
    volumes:
      - certs:/certs
      - ./config.json:/config/config.json:ro
    environment:
      # Real secrets live here -- never in the agent
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
    healthcheck:
      test: ["CMD", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:9000/healthz"]
      interval: 5s
      timeout: 3s
      start_period: 10s
      retries: 3

networks:
  agent_net:
    driver: bridge
    internal: true                             # no internet gateway

volumes:
  certs:
```

!!! info "What just happened?"

    The agent is on `agent_net`, which is `internal: true` -- Docker creates no
    gateway, so there is no route to the internet. `doubleagent` sits on both
    networks, making it the only way out. Real secrets are only in the
    `doubleagent` environment; the agent only sees placeholders.

## 2. Create `config.json`

This tells `doubleagent` how to handle outbound traffic: which domains to allow,
which to block, and where to inject real secrets.

A minimal config to get started:

```json
{
  "$schema": "./config/config.schema.json",
  "rules": [
    {
      "domains": ["api.openai.com"],
      "secrets": [
        {
          "placeholder": "PLACEHOLDER_OPENAI_KEY",
          "value_from_env": "OPENAI_API_KEY",
          "inject_in": ["header:Authorization"]
        }
      ]
    },
    {
      "domains": ["api.github.com"],
      "secrets": [
        {
          "placeholder": "PLACEHOLDER_GITHUB_TOKEN",
          "value_from_env": "GITHUB_TOKEN",
          "inject_in": ["header:Authorization"]
        }
      ]
    }
  ],
  "default_policy": "allow"
}
```

That is enough to get running. Once you are comfortable, you can add fine-grained
blocking rules -- see the [Configuration Reference](../configuration/index.md).

## 3. Start the stack

```bash
docker compose up
```

`doubleagent` exposes `GET /healthz` and `GET /readyz` on port `9000` by default.
Once healthy, all agent traffic flows through the proxy.

## Next steps

- [Add MCP servers](adding-mcp-servers.md) to your stack
- [Configure rules](../configuration/rules.md) for fine-grained request policies
- [Set up secret injection](../configuration/secrets.md) for all your API keys
- [Understand the architecture](../concepts/architecture.md) in detail
