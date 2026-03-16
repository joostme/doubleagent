#!/bin/sh
set -e

echo "doubleagent: starting up..."

# Ensure the certs directory exists
mkdir -p /certs

cleanup_iptables() {
  python -m doubleagent.main --cleanup-iptables "$@" >/dev/null 2>&1 || true
}

forward_signal() {
  sig="$1"
  if [ -n "${child_pid:-}" ]; then
    kill -"$sig" "$child_pid" 2>/dev/null || true
  fi
}

trap 'forward_signal TERM' TERM
trap 'forward_signal INT' INT
trap cleanup_iptables EXIT

# Remove any stale managed rules from a previous unclean shutdown.
cleanup_iptables

# Run the proxy supervisor. It configures iptables as root and launches
# mitmdump as the non-root proxy user.
PYTHONPATH=/app python -m doubleagent.main "$@" &
child_pid=$!
wait "$child_pid"
exit $?
