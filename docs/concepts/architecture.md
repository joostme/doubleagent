# Architecture

`doubleagent` is an explicit proxy sidecar designed for Docker Compose stacks
running AI agents. It enforces network-level isolation so that AI agents cannot
directly access the internet, while providing controlled, policy-based access
through the proxy.

## System overview

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

## Components

`doubleagent` is built on [mitmproxy](https://mitmproxy.org/), an HTTPS-intercepting
proxy, and uses [Pydantic](https://docs.pydantic.dev/) for configuration validation.

| Component | File | Description |
|---|---|---|
| Entry point | `doubleagent/main.py` | Starts mitmproxy with the doubleagent addon |
| Proxy addon | `doubleagent/addon.py` | mitmproxy addon that intercepts and processes requests |
| Configuration | `doubleagent/config.py` | Config loading, validation, and hot-reload via file watching |
| Policy engine | `doubleagent/policy.py` | Evaluates allow/block rules against incoming requests |
| Port forwarding | `doubleagent/forward.py` | TCP port forwarding using socat |
| CA management | `doubleagent/ca.py` | Generates and manages the CA certificate for HTTPS interception |
| Health checks | `doubleagent/health.py` | Exposes `/healthz` and `/readyz` endpoints on port 9000 |

## Request flow

1. The agent sends an HTTP(S) request to an external service
2. Because `HTTP_PROXY` / `HTTPS_PROXY` are set, the request goes to `doubleagent`
3. `doubleagent` looks up the target domain in the configured rules
4. If the request matches a **block** rule, it returns a configurable error response
5. If the request is allowed, `doubleagent` performs **secret injection** --
   replacing placeholder credentials with real ones
6. The request is forwarded to the actual destination
7. The response is passed back to the agent

## Health endpoints

`doubleagent` exposes two health endpoints on port `9000` (configurable via
`health_port`):

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Liveness check -- returns 200 if the process is running |
| `GET /readyz` | Readiness check -- returns 200 when the proxy is ready to accept traffic |

These are used in Docker health checks to ensure dependent services don't start
before `doubleagent` is ready.

## Limits

`doubleagent` improves safety, but it is not a perfect sandbox.

It helps protect real secrets and blocks direct outbound requests from the agent.
But if the agent can talk to other tools that themselves have internet access,
data can still leave through those tools.

`playwright-mcp` is one example. If the agent can use it, the agent may still be
able to leak information through that MCP server.

So `doubleagent` is best seen as a strong safety layer, not a 100% security
boundary.
