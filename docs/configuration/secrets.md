# Secret Injection

`doubleagent` can replace placeholder credentials with real secrets at the proxy
level. This means your AI agent never sees the real API keys -- it only knows
about placeholder values.

## How it works

1. Your agent container has environment variables like `OPENAI_API_KEY=PLACEHOLDER_OPENAI_KEY`
2. The agent sends requests using these placeholder values
3. `doubleagent` intercepts the request and replaces the placeholder with the real secret
4. The request reaches the API provider with valid credentials

```yaml
# The agent sees this:            # doubleagent holds this:
OPENAI_API_KEY=PLACEHOLDER        OPENAI_API_KEY=sk-real-key-here
```

## Injecting into headers

The most common pattern is injecting secrets into HTTP headers, such as
`Authorization`:

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
      ]
    }
  ]
}
```

If your client sends `Authorization: Bearer PLACEHOLDER_OPENAI_KEY`,
`doubleagent` only replaces the placeholder part. The `Bearer ` prefix stays
the same.

## Injecting into query parameters

Some APIs use query parameters for authentication:

```json
{
  "rules": [
    {
      "domains": ["api.example.com"],
      "secrets": [
        {
          "placeholder": "PLACEHOLDER_SEARCH_TOKEN",
          "value_from_env": "SEARCH_TOKEN",
          "inject_in": ["query:api_key"]
        }
      ]
    }
  ]
}
```

## Secret source

For each secret, specify either:

| Field | Description |
|---|---|
| `value_from_env` | Read the real secret from an environment variable on the `doubleagent` container |
| `value` | Inline the real secret directly in the config (not recommended for production) |

!!! warning

    Prefer `value_from_env` over `value`. Inlining secrets in your config file
    means they could be committed to version control. Use environment variables
    and a `.env` file instead.

## `inject_in` targets

The `inject_in` field accepts an array of targets:

| Target format | Description |
|---|---|
| `header:Name` | Replace the placeholder in the specified HTTP header |
| `query:param` | Replace the placeholder in the specified query parameter |

## Multiple secrets per domain

You can inject multiple secrets for the same domain:

```json
{
  "rules": [
    {
      "domains": ["api.example.com"],
      "secrets": [
        {
          "placeholder": "PLACEHOLDER_API_KEY",
          "value_from_env": "API_KEY",
          "inject_in": ["header:X-API-Key"]
        },
        {
          "placeholder": "PLACEHOLDER_API_SECRET",
          "value_from_env": "API_SECRET",
          "inject_in": ["header:X-API-Secret"]
        }
      ]
    }
  ]
}
```

## Compose setup

Real secrets are set as environment variables on the `doubleagent` service, not
on the agent:

```yaml
services:
  doubleagent:
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GITHUB_TOKEN=${GITHUB_TOKEN}

  ai-agent:
    environment:
      # Placeholders only
      - OPENAI_API_KEY=PLACEHOLDER_OPENAI_KEY
      - GITHUB_TOKEN=PLACEHOLDER_GITHUB_TOKEN
```

Store real secrets in a `.env` file (which should be in `.gitignore`):

```bash
OPENAI_API_KEY=sk-real-key-here
GITHUB_TOKEN=ghp_real-token-here
```
