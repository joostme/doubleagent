<h1 align="center">doubleagent</h1>

<p align="center">
  <img src="./doubleagent-logo.svg" width="160" alt="doubleagent logo" />
</p>

<p align="center">
<strong>The security gateway for AI agents that don't need to be trusted.</strong>
</p>

<p align="center">
Your AI agent gets internet access. Your AI agent does <em>not</em> get your secrets.<br/>
Drop <code>doubleagent</code> into any Docker Compose stack and lock things down in minutes.
</p>

---

## The Problem

You give your AI agent API keys for OpenAI, GitHub, Anthropic, and a dozen other services. It needs them to do its job. But that same agent also has **full, unrestricted internet access** and holds your **real credentials in plain text**.

What happens when it hallucinates a `curl` to the wrong endpoint? What happens when a prompt injection tells it to exfiltrate your secrets? What happens when it decides to `DELETE /repos/*` on GitHub?

**Nothing good.**

## The Fix

`doubleagent` sits between your AI agent and the internet. The agent lives in a sealed Docker network with **zero internet access**. Every outbound request must pass through `doubleagent`, where it gets inspected, filtered, and -- only if it passes your rules -- forwarded.

```text
               +----------------------+
               |      ai-agent        |
               |  internal only net   |
               +----------+-----------+
                          |
                          | agent_net (internal: true)
                          |
               +----------v-----------+
               |     doubleagent      |
               |    rules + secrets   |
               +----------+-----------+
                          |
                          | default bridge
                          |
               +----------v-----------+
               |       internet       |
               +----------------------+
```

This is not just a proxy your agent can opt out of. The Docker network topology is `internal: true` -- there is **no route to the internet** from the agent container. Even if the agent unsets `HTTP_PROXY`, opens raw sockets, or tries anything creative, packets have nowhere to go. `doubleagent` is the only way out.

## Why doubleagent

### Real secrets never touch the agent

Your agent sees `PLACEHOLDER_OPENAI_KEY`. The real key lives only on `doubleagent`. When a request goes out, `doubleagent` swaps the placeholder for the real credential at the proxy level. If the agent is fully compromised, your secrets are still safe.

```yaml
# The agent sees this:            # doubleagent holds this:
OPENAI_API_KEY=PLACEHOLDER        OPENAI_API_KEY=sk-real-key-here
```

### Block dangerous operations, allow everything else

Let the agent use the GitHub API freely -- but block `DELETE /repos/*/*` so it can never delete a repository. Allow OpenAI completions -- but block file deletion endpoints. Rules are per-domain, per-method, and per-path.

```json
{
  "domains": ["api.github.com"],
  "rules": [{ "policy": "block", "method": "DELETE", "path_pattern": "/repos/*/*" }]
}
```

### Network-level enforcement, not convention

Most proxy setups rely on the agent honoring `HTTP_PROXY` environment variables. `doubleagent` enforces isolation at the Docker network level. The agent container physically cannot reach the internet -- no matter what it tries.

### Drop-in sidecar for any stack

Already running an AI agent in Docker Compose? Add `doubleagent` in minutes. No agent code changes required. Just update your Compose file and create a `config.json`.

### Hot-reload config

Change your rules on the fly. `doubleagent` watches `config.json` and reloads automatically. If your new config is invalid, it keeps using the last working version.

---

## Quick Start

There are three things to set up: the **network isolation**, the **proxy config**, and the **secret handoff**. The examples below assume you already have an `ai-agent` service in Docker Compose.

### 1. Add `doubleagent` to your Compose file

This is the core of the setup. You are adding `doubleagent` as a sidecar, creating an isolated network, and wiring your agent through it.

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
    # entrypoint: ["/bin/sh", "-c", ". /certs/install-ca.sh && exec your-original-entrypoint"]
    environment:
      # Placeholders -- not real keys
      - OPENAI_API_KEY=PLACEHOLDER_OPENAI_KEY
      - GITHUB_TOKEN=PLACEHOLDER_GITHUB_TOKEN
      # Route traffic through doubleagent
      - HTTP_PROXY=http://doubleagent:8080
      - HTTPS_PROXY=http://doubleagent:8080
      - NO_PROXY=localhost,127.0.0.1

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

> **What just happened?** The agent is on `agent_net`, which is `internal: true` -- Docker creates no gateway, so there is no route to the internet. `doubleagent` sits on both networks, making it the only way out. Real secrets are only in the `doubleagent` environment; the agent only sees placeholders.

### 2. Create `config.json`

This tells `doubleagent` how to handle outbound traffic: which domains to allow, which to block, and where to inject real secrets.

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

That is enough to get running. Once you are comfortable, you can add fine-grained blocking rules -- see the [Config Reference](#config-reference) section below.

### 3. Start the stack

```bash
docker compose up
```

`doubleagent` exposes `GET /healthz` and `GET /readyz` on port `9000` by default. Once healthy, all agent traffic flows through the proxy.

### Optional: Adding MCP servers

If your agent uses MCP servers (like Playwright), they need to join both networks so the agent can reach them over `agent_net` while the MCP server itself retains internet access:

```yaml
services:
  playwright-mcp:
    image: my-playwright-mcp:latest
    networks:
      - default          # internet access for browser automation
      - agent_net        # reachable by ai-agent
    expose:
      - "8931"
```

Add the MCP host to `NO_PROXY` on the agent so local traffic stays inside Docker:

```yaml
- NO_PROXY=localhost,127.0.0.1,doubleagent,playwright-mcp
```

See `docker-compose.example.yml` and `config/config.example.json` for a complete working stack.

---

## Config Reference

`doubleagent` reads `config.json`. When the file changes, it reloads it automatically. If the new file is invalid, it keeps using the last working config.

If you want editor autocomplete and validation, add this near the top of your config file:

```json
{
  "$schema": "./config/config.schema.json"
}
```

### Main config fields

| Field | Description | Default |
|---|---|---|
| `rules` | Domain rules, secrets, and request policies | -- |
| `default_policy` | What happens when no rule matches: `allow` or `block` | -- |
| `http_port` | The proxy port | `8080` |
| `health_port` | The health endpoint port | `9000` |
| `forward_ports` | Ports that `doubleagent` should expose and forward to the agent | -- |
| `ca.cert_path` | Where the generated CA certificate is written | -- |

### Common rule examples

#### Only allow one provider and block everything else

```json
{
  "rules": [
    {
      "domains": ["api.openai.com"],
      "policy": "allow"
    }
  ],
  "default_policy": "block"
}
```

#### Block one whole domain

```json
{
  "rules": [
    {
      "domains": ["telemetry.example.com"],
      "policy": "block"
    }
  ]
}
```

#### Bypass MITM for a certificate-pinned domain

```json
{
  "rules": [
    {
      "domains": ["pinned.example.com"],
      "policy": "bypass"
    }
  ]
}
```

This tunnels traffic through `doubleagent` without TLS interception. Use it for domains that fail behind MITM because they use certificate pinning.

#### Inject a secret into a header

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
      ]
    }
  ]
}
```

If your client sends `Authorization: Bearer PLACEHOLDER_OPENAI_KEY`, `doubleagent` only replaces the placeholder part. The `Bearer ` prefix stays the same.

#### Inject a secret into a query parameter

```json
{
  "rules": [
    {
      "domains": ["api.example.com"],
      "secrets": [
        {
          "placeholder": "PLACEHOLDER_SEARCH_TOKEN",
          "value_from_env": "SEARCH_TOKEN",
          "inject_in": ["query:api_key"]
        }
      ]
    }
  ]
}
```

#### Block one dangerous endpoint

```json
{
  "rules": [
    {
      "domains": ["api.github.com"],
      "rules": [
        {
          "policy": "block",
          "method": "DELETE",
          "path_pattern": "/repos/*/*",
          "response": {
            "status": 403,
            "body": {
              "error": "blocked",
              "reason": "repository deletion is blocked by doubleagent policy"
            }
          }
        }
      ]
    }
  ]
}
```

#### Allow one safe request inside a blocked domain

```json
{
  "rules": [
    {
      "domains": ["api.example.com"],
      "policy": "block",
      "rules": [
        {
          "policy": "allow",
          "method": "GET",
          "path_pattern": "/healthz"
        }
      ]
    }
  ]
}
```

This is useful when you want to block most of a domain but still allow one small safe endpoint.

### Matching rules

- Use exact domains like `api.openai.com`.
- Use `*.example.com` if you want to match subdomains like `api.example.com`.
- `*.example.com` does not match the bare `example.com`.
- In `path_pattern`, `*` matches one path part and `**` can span across `/`.
- `inject_in` supports `header:Name` and `query:param`.
- For a secret, use either `value` or `value_from_env`.
- `bypass` is only valid for whole-domain rules. Bypassed domains cannot use nested request rules or secret injection because HTTPS traffic is tunneled without inspection.

If you have overlapping domain rules, put the more specific one first.

## Port Forwarding

Because `ai-agent` is on an internal-only network, it should not publish its own ports directly to the host. If you still want to reach something like the agent web UI, let `doubleagent` publish the port and forward it to the agent.

In `config.json`:

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

In Compose:

```yaml
services:
  doubleagent:
    ports:
      - "3000:3000"
```

Traffic flows like this:

```text
host:3000 -> doubleagent:3000 -> ai-agent:3000
```

This gives you access to the agent UI without moving the agent's container onto an internet-capable network.

## Limits

`doubleagent` improves safety, but it is not a perfect sandbox.

It helps protect real secrets and blocks direct outbound requests. But if the agent can talk to other tools that themselves have internet access, data can still leave through those tools.

`playwright-mcp` is one example. If the agent can use it, the agent may still be able to leak information through that MCP server.

So `doubleagent` is best seen as a strong safety layer, not a 100 percent security boundary.

## Troubleshooting

### TLS / certificate errors from the agent

`doubleagent` intercepts HTTPS traffic using a generated CA certificate. The agent container needs to trust this CA. If you see errors like:

```
SSL: CERTIFICATE_VERIFY_FAILED
unable to get local issuer certificate
self-signed certificate in certificate chain
```

the agent's runtime is not picking up the CA cert.

**Step 1: Run `install-ca.sh`.** The `doubleagent` image automatically publishes `install-ca.sh` into the shared `certs` volume. This script installs the CA into the OS trust store AND sets the runtime-specific env vars (`NODE_EXTRA_CA_CERTS`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE`, `GIT_SSL_CAINFO`) — so you don't need to add them to your Compose file. The vars are persisted to `/etc/environment` and `/etc/profile.d/` so they work even when the process runs as a non-root user.

Source the script in your entrypoint (note the `.` — required so exports are inherited by `exec`):

```yaml
services:
  ai-agent:
    volumes:
      - certs:/certs:ro
    entrypoint: ["/bin/sh", "-c", ". /certs/install-ca.sh && exec your-original-entrypoint"]
```

Replace `your-original-entrypoint` with whatever the agent image normally runs (check with `docker inspect <image>` if unsure). If a variable is already set in your Compose `environment`, `install-ca.sh` will not overwrite it.

### Agent can still reach the internet

If the agent bypasses the proxy, double-check that:

- The `agent_net` network has `internal: true` set.
- The agent service is **only** on `agent_net` (not also on `default`).
- There are no other networks attached to the agent that have a gateway.

### Config changes are not taking effect

`doubleagent` hot-reloads `config.json` on file change. If a reload fails (invalid JSON, schema violation), it keeps the last working config and logs a warning. Check the `doubleagent` container logs for reload errors.

## Development

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Or:

```bash
make install
make test
```

Run locally:

```bash
PYTHONPATH=. python -m doubleagent.main --config /config/config.json
```

See `docker-compose.example.yml` and `config/config.example.json` for complete examples.
