# Troubleshooting

## TLS / certificate errors from the agent

`doubleagent` intercepts HTTPS traffic using a generated CA certificate. The
agent container needs to trust this CA. If you see errors like:

```
SSL: CERTIFICATE_VERIFY_FAILED
unable to get local issuer certificate
self-signed certificate in certificate chain
```

the agent's runtime is not picking up the CA cert.

### Step 1: Check the environment variables

The Compose example sets several environment variables that cover the most
common runtimes:

| Variable | Runtime |
|---|---|
| `NODE_EXTRA_CA_CERTS` | Node.js |
| `REQUESTS_CA_BUNDLE` | Python `requests` |
| `SSL_CERT_FILE` | OpenSSL-based tools |
| `CURL_CA_BUNDLE` | curl |
| `GIT_SSL_CAINFO` | git |

All should point to `/certs/ca.crt`:

```yaml
environment:
  - NODE_EXTRA_CA_CERTS=/certs/ca.crt
  - REQUESTS_CA_BUNDLE=/certs/ca.crt
  - SSL_CERT_FILE=/certs/ca.crt
  - CURL_CA_BUNDLE=/certs/ca.crt
  - GIT_SSL_CAINFO=/certs/ca.crt
```

### Step 2: Install the CA into the system trust store

Some runtimes and tools ignore the environment variables and only check the OS
trust store. In that case, run a CA install step before the agent starts.

The `doubleagent` image automatically publishes `install-ca.sh` into the shared
`certs` volume on startup. This script auto-detects the OS (Debian, Ubuntu,
Alpine, RHEL, Fedora, CentOS, Amazon Linux, SUSE) and installs the cert into the
right location. It also handles Java keystores if `keytool` is available.

Since your agent container already mounts the `certs` volume, the script is
available at `/certs/install-ca.sh` with no extra setup. Override the agent's
entrypoint to run it first:

```yaml
services:
  ai-agent:
    volumes:
      - certs:/certs:ro
    entrypoint: ["/bin/sh", "-c", "/certs/install-ca.sh && exec your-original-entrypoint"]
```

Replace `your-original-entrypoint` with whatever the agent image normally runs.
Check with `docker inspect <image>` if unsure.

## Agent can still reach the internet

If the agent bypasses the proxy, verify:

- [ ] The `agent_net` network has `internal: true` set
- [ ] The agent service is **only** on `agent_net` (not also on `default`)
- [ ] There are no other networks attached to the agent that have a gateway

You can check the agent's network configuration:

```bash
docker inspect <agent-container> | jq '.[0].NetworkSettings.Networks'
```

## Config changes are not taking effect

`doubleagent` hot-reloads `config.json` on file change. If a reload fails
(invalid JSON, schema violation), it keeps the last working config and logs a
warning.

Check the `doubleagent` container logs for reload errors:

```bash
docker compose logs doubleagent | grep -i reload
```

Common causes:

- **Invalid JSON** -- missing comma, trailing comma, unquoted key
- **Schema violation** -- unknown field, wrong type, missing required field
- **File not mounted** -- verify the volume mount in your Compose file
