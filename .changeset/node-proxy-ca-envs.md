---
"doubleagent": patch
---

Document and configure Node.js proxy and CA environment variables more completely.

`install-ca.sh` now sets `NODE_USE_ENV_PROXY=1` so Node.js honors `HTTP_PROXY`, `HTTPS_PROXY`, and `NO_PROXY`, and `NODE_USE_SYSTEM_CA=1` so Node can use the OS trust store after the proxy CA is installed. The docs and Compose example were also updated to explain how those settings work alongside `NODE_EXTRA_CA_CERTS`.
