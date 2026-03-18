# Rules

Rules let you control which HTTP requests are allowed or blocked on a per-domain,
per-method, and per-path basis.

## Domain-level rules

### Allow a single provider, block everything else

```json
{
  "rules": [
    {
      "domains": ["api.openai.com"],
      "policy": "allow"
    }
  ],
  "default_policy": "block"
}
```

### Block an entire domain

```json
{
  "rules": [
    {
      "domains": ["telemetry.example.com"],
      "policy": "block"
    }
  ]
}
```

## Path-level rules

### Block a dangerous endpoint

Allow GitHub API access generally, but block repository deletion:

```json
{
  "rules": [
    {
      "domains": ["api.github.com"],
      "rules": [
        {
          "policy": "block",
          "method": "DELETE",
          "path_pattern": "/repos/*/*",
          "response": {
            "status": 403,
            "body": {
              "error": "blocked",
              "reason": "repository deletion is blocked by doubleagent policy"
            }
          }
        }
      ]
    }
  ]
}
```

### Allow a safe endpoint inside a blocked domain

```json
{
  "rules": [
    {
      "domains": ["api.example.com"],
      "policy": "block",
      "rules": [
        {
          "policy": "allow",
          "method": "GET",
          "path_pattern": "/healthz"
        }
      ]
    }
  ]
}
```

This is useful when you want to block most of a domain but still allow one small
safe endpoint.

## Matching behavior

| Pattern | Behavior |
|---|---|
| `api.openai.com` | Exact domain match |
| `*.example.com` | Matches subdomains like `api.example.com` |
| `*.example.com` | Does **not** match bare `example.com` |
| `*` in `path_pattern` | Matches one path segment |
| `**` in `path_pattern` | Matches across `/` separators |

## Rule evaluation order

- More specific rules (path-level) take priority over domain-level policies
- If you have overlapping domain rules, put the more specific one first
- If no rule matches a request, `default_policy` determines the outcome

## Custom block responses

When blocking a request, you can specify a custom response:

```json
{
  "policy": "block",
  "method": "DELETE",
  "path_pattern": "/repos/*/*",
  "response": {
    "status": 403,
    "body": {
      "error": "blocked",
      "reason": "repository deletion is blocked by doubleagent policy"
    }
  }
}
```

The `response` object supports:

- `status` -- HTTP status code to return
- `body` -- JSON object to return as the response body
