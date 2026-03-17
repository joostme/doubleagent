# doubleagent

An explicit proxy sidecar for AI containers. It swaps placeholder secrets for real ones and blocks unsafe requests before they leave the stack.

## What it does

- The AI agent uses `HTTP_PROXY` and `HTTPS_PROXY` to talk to `doubleagent`.
- The AI only sees placeholder keys in its own environment.
- `doubleagent` replaces placeholders in headers or query params.
- `doubleagent` can block requests by method and path.
- Mitmproxy generates the CA; `doubleagent` exports it to `/certs/ca.crt` for the AI container to trust.

## Quick start

**1. Create a config file**

```json
{
  "rules": [
    {
      "domains": ["api.openai.com"],
      "secrets": [
        {
          "placeholder": "PLACEHOLDER_OPENAI_KEY",
          "value_from_env": "OPENAI_API_KEY",
          "inject_in": ["header:Authorization"]
        }
      ],
      "block": [
        {
          "method": "DELETE",
          "path_pattern": "/v1/files/*",
          "response": {
            "status": 403,
            "body": {"error": "blocked by doubleagent"}
          }
        }
      ]
    }
  ],
  "default_policy": "allow"
}
```

**2. Add the sidecar to Compose**

```yaml
services:
  doubleagent:
    build: .
    volumes:
      - certs:/certs
      - ./config.json:/config/config.json:ro
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}

  ai-agent:
    image: your-ai-agent:latest
    depends_on:
      doubleagent:
        condition: service_healthy
    volumes:
      - certs:/certs:ro
    environment:
      - OPENAI_API_KEY=Bearer PLACEHOLDER_OPENAI_KEY
      - HTTP_PROXY=http://doubleagent:8080
      - HTTPS_PROXY=http://doubleagent:8080
      - NO_PROXY=localhost,127.0.0.1
      - NODE_EXTRA_CA_CERTS=/certs/ca.crt
      - REQUESTS_CA_BUNDLE=/certs/ca.crt
      - SSL_CERT_FILE=/certs/ca.crt
      - CURL_CA_BUNDLE=/certs/ca.crt
      - GIT_SSL_CAINFO=/certs/ca.crt

volumes:
  certs:
```

**3. Run it**

```bash
docker compose up
```

## Development

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Or use:

```bash
make install
make test
```

Run locally:

```bash
PYTHONPATH=. python -m doubleagent.main --config /config/config.json
```

## Config reference

If you want editor autocomplete and validation for a root-level `config.json`, add this as the first property in the file:

```json
{
  "$schema": "./config/config.schema.json",
  "...": "rest of your config"
}
```

Secret injection supports:

- `header:Name` - replace a placeholder in a header value
- `query:param` - replace a placeholder in a query parameter

Secrets can use `value` or `value_from_env`. If you need fixed text around the placeholder, include it in the original value, for example `Bearer PLACEHOLDER_OPENAI_KEY`.

Block rules match HTTP method and glob path pattern. Allow rules override block rules.

`default_policy` is `allow` or `block`.
