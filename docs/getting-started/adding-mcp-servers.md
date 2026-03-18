# Adding MCP Servers

If your agent uses MCP servers (like Playwright), they need to join both networks
so the agent can reach them over `agent_net` while the MCP server itself retains
internet access.

## Compose configuration

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

## Update `NO_PROXY`

Add the MCP host to `NO_PROXY` on the agent so local traffic stays inside Docker:

```yaml
environment:
  - NO_PROXY=localhost,127.0.0.1,doubleagent,playwright-mcp
```

!!! tip

    See `docker-compose.example.yml` and `config/config.example.json` in the
    repository for a complete working stack that includes Playwright MCP.

## How it works

MCP servers sit on both networks:

- **`default`** -- gives them internet access (e.g., for browser automation)
- **`agent_net`** -- makes them reachable by the agent container

Since the agent communicates with MCP servers over the internal network, this
traffic does not pass through `doubleagent`. The `NO_PROXY` setting ensures
the agent's HTTP client sends these requests directly rather than through the
proxy.

!!! warning "Security consideration"

    If the agent can use an MCP server that has internet access, the agent may
    still be able to leak information through that MCP server. `doubleagent`
    blocks direct outbound requests from the agent, but cannot control what
    MCP servers do with the data they receive. See [Limits](../concepts/architecture.md#limits)
    for more details.
