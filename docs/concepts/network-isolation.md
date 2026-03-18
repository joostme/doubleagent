# Network Isolation

The core security model of `doubleagent` relies on Docker's network isolation
capabilities. This is not a software-level proxy that agents can opt out of --
it is enforced at the network topology level.

## How Docker internal networks work

When you create a Docker network with `internal: true`, Docker does **not**
create a gateway interface. Without a gateway, containers on that network have
no route to any external IP address. Packets simply have nowhere to go.

```yaml
networks:
  agent_net:
    driver: bridge
    internal: true    # no internet gateway
```

## The dual-network pattern

`doubleagent` connects to two networks:

1. **`default`** -- the standard Docker bridge network with internet access
2. **`agent_net`** -- the internal-only network where the agent lives

```yaml
services:
  doubleagent:
    networks:
      - default       # has internet access
      - agent_net     # can talk to the agent

  ai-agent:
    networks:
      - agent_net     # internal only, no internet
```

This means:

- The agent can reach `doubleagent` over `agent_net`
- `doubleagent` can reach the internet over `default`
- The agent **cannot** reach the internet directly

## Why this matters

Most proxy setups rely on the agent honoring `HTTP_PROXY` environment variables.
An agent could simply:

- Unset `HTTP_PROXY`
- Open raw TCP sockets
- Use libraries that ignore proxy settings
- Deliberately bypass the proxy

With `doubleagent`'s network isolation, none of this works. Even if the agent
removes every proxy setting and tries to connect directly to any IP address, the
packets are dropped because the internal network has no route out.

## Verifying isolation

You can verify that network isolation is working by exec'ing into the agent
container and trying to reach the internet directly:

```bash
# This should fail -- no route to host
docker exec ai-agent curl -x "" https://api.openai.com

# This should work -- goes through the proxy
docker exec ai-agent curl https://api.openai.com
```

## Common mistakes

!!! warning "Agent on the wrong network"

    If the agent is on both `agent_net` and `default`, it can bypass
    `doubleagent` entirely. Make sure the agent is **only** on `agent_net`.

!!! warning "Other networks with gateways"

    If the agent has any other network attached that has a gateway, it can route
    traffic through that network instead. Check with:

    ```bash
    docker inspect <agent-container> | jq '.[0].NetworkSettings.Networks'
    ```
