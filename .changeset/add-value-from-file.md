---
"doubleagent": minor
---

Add `value_from_file` secret source for Docker secrets support

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
