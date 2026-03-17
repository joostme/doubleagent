#!/bin/sh
set -e

echo "doubleagent: starting up..."

mkdir -p /certs

exec env PYTHONPATH=/app python -m doubleagent.main "$@"
