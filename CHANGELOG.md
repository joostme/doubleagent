# doubleagent

## 1.0.0

### Minor Changes

- Initial release of doubleagent - an explicit proxy sidecar that isolates AI agent containers from the internet, enforcing request-level allow/block policies and injecting secrets at the proxy layer.

  - HTTPS-intercepting proxy via mitmproxy with per-domain allow/block policy rules
  - Secret injection into agent requests at the proxy layer, keeping credentials out of the agent container
  - TCP port forwarding via socat for exposing agent services through the gateway
  - Hot-reloadable JSON configuration with JSON Schema validation
  - Health check endpoints (`/healthz` and `/readyz`) for container orchestration
  - Multi-distro CA certificate installer script for agent containers
  - Docker image published to GHCR for linux/amd64 and linux/arm64
