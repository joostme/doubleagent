# Configuration Reference

`doubleagent` reads `config.json`. When the file changes, it reloads
automatically. If the new config is invalid, it keeps using the last working
version and logs a warning.

For editor autocomplete and validation, add this to your config file:

```json
{
  "$schema": "./config/config.schema.json"
}
```

## Main fields

| Field | Description | Default |
|---|---|---|
| `rules` | Domain rules, secrets, and request policies | -- |
| `default_policy` | What happens when no rule matches: `allow` or `block` | -- |
| `http_port` | The proxy port | `8080` |
| `health_port` | The health endpoint port | `9000` |
| `forward_ports` | Ports that `doubleagent` should expose and forward to the agent | -- |
| `ca.cert_path` | Where the generated CA certificate is written | -- |

## Minimal example

```json
{
  "$schema": "./config/config.schema.json",
  "rules": [
    {
      "domains": ["api.openai.com"],
      "policy": "allow"
    }
  ],
  "default_policy": "block"
}
```

This allows only `api.openai.com` and blocks everything else.

## Detailed guides

- [Rules](rules.md) -- per-domain, per-method, per-path request policies
- [Secrets](secrets.md) -- credential injection into headers and query parameters
- [Port forwarding](port-forwarding.md) -- expose agent services to the host

## Hot reload

`doubleagent` watches `config.json` for changes and reloads automatically. If
the new file is invalid (bad JSON, schema violation), it keeps the last working
config and logs a warning. Check container logs if changes don't seem to take
effect.
