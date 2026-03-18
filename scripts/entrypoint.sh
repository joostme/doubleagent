#!/bin/sh
set -e

echo "doubleagent: starting up..."

mkdir -p /certs

# Publish install-ca.sh into the shared certs volume so agent containers
# can run it without needing to clone the repo or copy files manually.
cp /scripts/install-ca.sh /certs/install-ca.sh
chmod +x /certs/install-ca.sh

exec env PYTHONPATH=/app python -m doubleagent.main "$@"
