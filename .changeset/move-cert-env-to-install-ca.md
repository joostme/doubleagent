---
"doubleagent": minor
---

`install-ca.sh` now sets the certificate environment variables (`NODE_EXTRA_CA_CERTS`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE`, `GIT_SSL_CAINFO`) automatically. You no longer need to list them in your Compose file — just source the script in your agent's entrypoint.

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
