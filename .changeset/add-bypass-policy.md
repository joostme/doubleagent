---
"doubleagent": minor
---

Add a new domain-level `bypass` policy for certificate-pinned services that cannot work behind TLS interception. When a rule uses `"policy": "bypass"`, doubleagent tunnels that domain through mitmproxy without MITM, so the upstream certificate is presented unchanged to the client.

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
