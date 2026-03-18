# doubleagent

`doubleagent` is a proxy sidecar for AI agent containers. It increases security by narrowing what the agent can call, keeps real secrets out of the agents container, and gives you granular control over domains, methods, paths, secret injection, and port forwarding.

The core idea: Put your AI agent in a closed network with no direct internet access, then make `doubleagent` act as a secure gateway.

## Features

- Keeps your agent off the public internet and sends outbound traffic through the `doubleagent` proxy.
- Keeps real API keys out of your agents container by storing them on `doubleagent` and swapping in placeholders.
- Lets you allow or block specific domains, endpoints, and request types.
- Can expose ports through `doubleagent` without giving the agent direct internet access.
- Gives you simple config for secrets, request rules, and default allow or block behavior.

## How it works

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

This works because of the network setup, not just because of proxy environment variables. `ai-agent` only sits on `agent_net`, and that network is marked `internal: true`, so the agent has no direct route to the internet. `doubleagent` sits on both networks, which makes it the only way out. It can inspect requests, inject secrets, block calls, and forward the rest.

Even if the agent ignores `HTTP_PROXY` or tries to open its own connection, it still has no direct internet route from inside the Docker network.

## Add it to an existing Compose stack

The examples below assume you already have an `ai-agent` service in your `docker-compose.yml` and want to add `doubleagent` next to it.

### 1. Create `config.json`

Start with `config/config.example.json` or use a small config like this:

```json
{
  "$schema": "./config/config.schema.json",
  "http_port": 8080,
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
          "path_pattern": "/v1/files/**",
          "response": {
            "status": 403,
            "body": {
              "error": "blocked",
              "reason": "file deletion is blocked by doubleagent policy"
            }
          }
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

### 2. Update your Compose file

If your current stack looks roughly like this:

```yaml
services:
  ai-agent:
    image: my-ai-agent:latest
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
```

add or change these lines:

```diff
 services:
   ai-agent:
     image: my-ai-agent:latest
+    networks:
+      - agent_net
+    depends_on:
+      doubleagent:
+        condition: service_healthy
+    volumes:
+      - certs:/certs:ro
     environment:
-      - OPENAI_API_KEY=${OPENAI_API_KEY}
-      - GITHUB_TOKEN=${GITHUB_TOKEN}
+      - OPENAI_API_KEY=PLACEHOLDER_OPENAI_KEY
+      - GITHUB_TOKEN=PLACEHOLDER_GITHUB_TOKEN
+      - HTTP_PROXY=http://doubleagent:8080
+      - HTTPS_PROXY=http://doubleagent:8080
+      - NO_PROXY=localhost,127.0.0.1,doubleagent,playwright-mcp
+      - NODE_EXTRA_CA_CERTS=/certs/ca.crt
+      - REQUESTS_CA_BUNDLE=/certs/ca.crt
+      - SSL_CERT_FILE=/certs/ca.crt
+      - CURL_CA_BUNDLE=/certs/ca.crt
+      - GIT_SSL_CAINFO=/certs/ca.crt
+      - PLAYWRIGHT_MCP_URL=http://playwright-mcp:8931
+
+  doubleagent:
+    build: .
+    networks:
+      - default
+      - agent_net
+    volumes:
+      - certs:/certs
+      - ./config.json:/config/config.json:ro
+    environment:
+      - OPENAI_API_KEY=${OPENAI_API_KEY}
+      - GITHUB_TOKEN=${GITHUB_TOKEN}
+    healthcheck:
+      test: ["CMD", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:9000/healthz"]
+      interval: 5s
+      timeout: 3s
+      start_period: 10s
+      retries: 3
+
+  playwright-mcp:
+    image: my-playwright-mcp:latest
+    networks:
+      - default
+      - agent_net
+    expose:
+      - "8931"
+
+networks:
+  agent_net:
+    driver: bridge
+    internal: true
+
+volumes:
+  certs:
```

If you already have `networks:` or `volumes:` sections, merge these lines into the existing ones.

### 3. Move your real secrets to `doubleagent`

The main change is simple: the agents container stops seeing the real secrets.

Before:

```yaml
services:
  ai-agent:
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
```

After:

```yaml
services:
  ai-agent:
    environment:
      - OPENAI_API_KEY=PLACEHOLDER_OPENAI_KEY
      - GITHUB_TOKEN=PLACEHOLDER_GITHUB_TOKEN

  doubleagent:
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
```

`doubleagent` then replaces those placeholders in outbound requests based on your `config.json`.

### 4. Adding a MCP server

The `playwright-mcp` example joins both networks:

- `agent_net`, so `ai-agent` can reach it as `http://playwright-mcp:8931`
- `default`, so the MCP server itself can still access the internet

This means the agent can talk to the MCP server over the internal Docker network, while the MCP server itself can still use the internet. The `NO_PROXY` entry makes sure local traffic to `playwright-mcp` stays inside Docker instead of being sent through `doubleagent`.

### 5. Start the stack

```bash
docker compose up
```

`doubleagent` exposes `GET /healthz` and `GET /readyz` on port `9000` by default.

## Config

`doubleagent` reads `config.json`. When the file changes, it reloads it automatically. If the new file is invalid, it keeps using the last working config.

If you want editor autocomplete and validation, add this near the top of your config file:

```json
{
  "$schema": "./config/config.schema.json"
}
```

### Main config fields

- `rules`: where you define domains, secrets, and request rules.
- `default_policy`: what happens when no rule matches. Use `allow` or `block`.
- `http_port`: the proxy port. Default: `8080`.
- `health_port`: the health endpoint port. Default: `9000`.
- `forward_ports`: ports that `doubleagent` should expose and forward to the agent.
- `ca.cert_path`: where the generated CA certificate is written.

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

### A few matching rules

- Use exact domains like `api.openai.com`.
- Use `*.example.com` if you want to match subdomains like `api.example.com`.
- `*.example.com` does not match the bare `example.com`.
- In `path_pattern`, `*` matches one path part and `**` can span across `/`.
- `inject_in` supports `header:Name` and `query:param`.
- For a secret, use either `value` or `value_from_env`.

If you have overlapping domain rules, put the more specific one first.

## Port forwarding

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

This gives you access to the agent UI without moving the agents container onto an internet-capable network.

## Limits

`doubleagent` improves safety, but it is not a perfect sandbox.

It helps protect real secrets and blocks direct outbound requests. But if the agent can talk to other tools that themselves have internet access, data can still leave through those tools.

`playwright-mcp` is one example. If the agent can use it, the agent may still be able to leak information through that MCP server.

So `doubleagent` is best seen as a strong safety layer, not a 100 percent security boundary.

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
