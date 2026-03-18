# Getting Started

Get up and running with `doubleagent` in minutes.

There are three things to set up: the **network isolation**, the **proxy config**,
and the **secret handoff**. Follow the [quick start guide](quick-start.md) for
step-by-step instructions.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and
  [Docker Compose](https://docs.docker.com/compose/install/) installed on your system
- An existing AI agent running in Docker Compose (or one you want to containerize)
- API keys / secrets you want to protect

## How It Works (in 30 seconds)

1. Your AI agent runs on an **internal-only Docker network** with no internet gateway
2. `doubleagent` sits on both the internal network and the default network (with internet)
3. All outbound traffic from the agent must pass through `doubleagent`
4. `doubleagent` inspects each request, applies your rules, swaps placeholder
   credentials for real ones, and forwards allowed requests

The agent never sees your real secrets, and it can never bypass the proxy --
the network topology enforces this at the Docker level.
