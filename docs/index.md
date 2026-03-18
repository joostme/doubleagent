---
hide:
  - navigation
  - toc
---

# doubleagent

**The security gateway for AI agents that don't need to be trusted.**

Your AI agent gets internet access. Your AI agent does *not* get your secrets.
Drop `doubleagent` into any Docker Compose stack and lock things down in minutes.

---

<div class="grid cards" markdown>

-   :material-shield-lock:{ .lg .middle } **Real secrets never touch the agent**

    ---

    Your agent sees placeholder credentials. The real keys live only on
    `doubleagent` and are swapped in at the proxy level.

    [:octicons-arrow-right-24: How secret injection works](concepts/secret-injection.md)

-   :material-network-outline:{ .lg .middle } **Network-level enforcement**

    ---

    The agent container physically cannot reach the internet. Docker's
    `internal: true` network means there is no route out -- `doubleagent` is
    the only gateway.

    [:octicons-arrow-right-24: Architecture](concepts/architecture.md)

-   :material-filter:{ .lg .middle } **Fine-grained request policies**

    ---

    Allow the GitHub API but block `DELETE /repos/*/*`. Allow OpenAI completions
    but block file deletion. Rules are per-domain, per-method, per-path.

    [:octicons-arrow-right-24: Configuration](configuration/index.md)

-   :material-rocket-launch:{ .lg .middle } **Drop-in sidecar**

    ---

    Already running an AI agent in Docker Compose? Add `doubleagent` in minutes.
    No agent code changes required.

    [:octicons-arrow-right-24: Quick start](getting-started/quick-start.md)

</div>

## The Problem

You give your AI agent API keys for OpenAI, GitHub, Anthropic, and a dozen other
services. It needs them to do its job. But that same agent also has **full,
unrestricted internet access** and holds your **real credentials in plain text**.

What happens when it hallucinates a `curl` to the wrong endpoint? What happens
when a prompt injection tells it to exfiltrate your secrets? What happens when it
decides to `DELETE /repos/*` on GitHub?

**Nothing good.**

## The Fix

`doubleagent` sits between your AI agent and the internet. The agent lives in a
sealed Docker network with **zero internet access**. Every outbound request must
pass through `doubleagent`, where it gets inspected, filtered, and -- only if it
passes your rules -- forwarded.

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

This is not just a proxy your agent can opt out of. The Docker network topology
is `internal: true` -- there is **no route to the internet** from the agent
container. Even if the agent unsets `HTTP_PROXY`, opens raw sockets, or tries
anything creative, packets have nowhere to go. `doubleagent` is the only way out.
