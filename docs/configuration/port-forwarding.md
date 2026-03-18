# Port Forwarding

Because `ai-agent` is on an internal-only network, it should not publish its own
ports directly to the host. If you still want to reach something like the agent's
web UI, let `doubleagent` publish the port and forward it to the agent.

## Configuration

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

In your Compose file:

```yaml
services:
  doubleagent:
    ports:
      - "3000:3000"
```

## How it works

Traffic flows like this:

```text
host:3000 -> doubleagent:3000 -> ai-agent:3000
```

`doubleagent` uses `socat` internally to forward TCP connections from its
`listen_port` to the `target_host:target_port` on the internal network.

This gives you access to the agent's UI (or any other TCP service) without
moving the agent container onto an internet-capable network.

## Multiple ports

You can forward multiple ports:

```json
{
  "forward_ports": [
    {
      "listen_port": 3000,
      "target_host": "ai-agent",
      "target_port": 3000
    },
    {
      "listen_port": 8080,
      "target_host": "ai-agent",
      "target_port": 8080
    }
  ]
}
```

Remember to publish each port in the Compose file:

```yaml
services:
  doubleagent:
    ports:
      - "3000:3000"
      - "8080:8080"
```

## Forwarding to other services

Port forwarding is not limited to the agent. You can forward to any service on
the internal network:

```json
{
  "forward_ports": [
    {
      "listen_port": 5432,
      "target_host": "postgres",
      "target_port": 5432
    }
  ]
}
```
