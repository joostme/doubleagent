# doubleagent

## 1.2.0

### Minor Changes

- 767f339: Add `value_from_file` secret source for Docker secrets support

  Secrets can now be read from a file path via the new `value_from_file` field on secret rules. This is designed for use with Docker secrets, which are mounted at `/run/secrets/<name>` inside the container, but works with any file.

  Each secret must still specify exactly one source: `value`, `value_from_env`, or `value_from_file`.

  Example config:

  ```json
  {
    "placeholder": "PLACEHOLDER_OPENAI_KEY",
    "value_from_file": "/run/secrets/openai_api_key",
    "inject_in": ["header:Authorization"]
  }
  ```

  Example docker-compose.yml:

  ```yaml
  services:
    doubleagent:
      secrets:
        - openai_api_key

  secrets:
    openai_api_key:
      environment: OPENAI_API_KEY
  ```

## 1.1.0

### Minor Changes

- 38674d7: Add a new domain-level `bypass` policy for certificate-pinned services that cannot work behind TLS interception. When a rule uses `"policy": "bypass"`, doubleagent tunnels that domain through mitmproxy without MITM, so the upstream certificate is presented unchanged to the client.

  Use `bypass` for pinned domains like this:

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

  Because bypassed traffic is not decrypted, those rules cannot use secret injection or nested request-level rules.

- b1f6929: `install-ca.sh` now sets the certificate environment variables (`NODE_EXTRA_CA_CERTS`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE`, `GIT_SSL_CAINFO`) automatically. You no longer need to list them in your Compose file — just source the script in your agent's entrypoint.

  The variables are exported in the current shell (inherited by `exec`), written to `/etc/environment`, and written to `/etc/profile.d/doubleagent-ca.sh` so they work even when the entrypoint runs as root but the process runs as another user. Variables that are already set (e.g. via Compose `environment`) are not overwritten.

  **Migration:** remove the five certificate env vars from your `ai-agent` service and source `install-ca.sh` in the entrypoint:

  ```diff
   services:
     ai-agent:
       volumes:
         - certs:/certs:ro
  -    # entrypoint: ["/bin/sh", "-c", "/certs/install-ca.sh && exec your-original-entrypoint"]
  +    entrypoint: ["/bin/sh", "-c", ". /certs/install-ca.sh && exec your-original-entrypoint"]
       environment:
         - HTTP_PROXY=http://doubleagent:8080
         - HTTPS_PROXY=http://doubleagent:8080
         - NO_PROXY=localhost,127.0.0.1,doubleagent
  -      - NODE_EXTRA_CA_CERTS=/certs/ca.crt
  -      - REQUESTS_CA_BUNDLE=/certs/ca.crt
  -      - SSL_CERT_FILE=/certs/ca.crt
  -      - CURL_CA_BUNDLE=/certs/ca.crt
  -      - GIT_SSL_CAINFO=/certs/ca.crt
  ```

  Note the `.` (dot-source) before `/certs/install-ca.sh` — this is required so the `export`s happen in the current shell and are inherited by the `exec`'d process.

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
