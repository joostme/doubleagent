# Development

## Prerequisites

- Python >= 3.14
- pip or make

## Setup

Install dependencies:

=== "pip"

    ```bash
    python -m pip install -r requirements.txt
    ```

=== "make"

    ```bash
    make install
    ```

## Running tests

=== "unittest"

    ```bash
    python -m unittest discover -s tests -v
    ```

=== "make"

    ```bash
    make test
    ```

## Running locally

```bash
PYTHONPATH=. python -m doubleagent.main --config /config/config.json
```

## Project structure

```text
doubleagent/
  main.py           # Entry point -- starts mitmproxy
  addon.py          # mitmproxy addon for request interception
  config.py         # Configuration loading and hot-reload
  policy.py         # Allow/block rule evaluation
  forward.py        # TCP port forwarding via socat
  ca.py             # CA certificate generation
  health.py         # Health check endpoints (/healthz, /readyz)
  logging_utils.py  # Logging utilities

scripts/
  entrypoint.sh     # Docker container entrypoint
  install-ca.sh     # Multi-distro CA certificate installer

tests/
  test_main.py
  test_config.py
  test_policy.py
  test_forward.py
  test_proxy_runtime.py
  test_integration.py

config/
  config.schema.json   # JSON Schema for config validation
  config.example.json  # Complete example configuration
```

## Key dependencies

| Package | Version | Purpose |
|---|---|---|
| [mitmproxy](https://mitmproxy.org/) | >= 12, < 13 | HTTPS-intercepting proxy |
| [Pydantic](https://docs.pydantic.dev/) | >= 2, < 3 | Configuration parsing and validation |

## Docker build

The project uses a `python:3.14-slim` base image. The Dockerfile installs `socat`
(for port forwarding) and `wget` (for health checks).

```bash
docker build -t doubleagent .
```

## Release process

Releases are managed with [Changesets](https://github.com/changesets/changesets).
The GitHub Actions workflow in `.github/workflows/release.yml` handles:

1. Running changesets to determine version bumps
2. Creating GitHub releases
3. Building and pushing multi-arch Docker images to GHCR

See `docker-compose.example.yml` and `config/config.example.json` for complete
working examples.
