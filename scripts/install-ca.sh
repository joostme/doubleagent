#!/bin/sh
# install-ca.sh — Install the doubleagent CA certificate into the system trust store.
#
# Supports: Debian/Ubuntu, Alpine, RHEL/Fedora/CentOS, Amazon Linux, SUSE.
# Run this in the AI container's entrypoint before any network calls.
#
# Usage:
#   /scripts/install-ca.sh [path-to-ca.crt]
#
# If no path is given, defaults to /usr/local/share/ca-certificates/doubleagent/ca.crt
# (the standard mount point from docker-compose.example.yml).

set -e

CA_CERT="${1:-/usr/local/share/ca-certificates/doubleagent/ca.crt}"

if [ ! -f "$CA_CERT" ]; then
    echo "doubleagent: CA cert not found at $CA_CERT — skipping trust store install."
    echo "doubleagent: The proxy may still work if runtime-specific env vars are set"
    echo "doubleagent: (NODE_EXTRA_CA_CERTS, REQUESTS_CA_BUNDLE, SSL_CERT_FILE)."
    exit 0
fi

echo "doubleagent: installing CA certificate from $CA_CERT"

# Detect the OS and install accordingly
if [ -f /etc/debian_version ]; then
    # Debian / Ubuntu
    cp "$CA_CERT" /usr/local/share/ca-certificates/doubleagent-ca.crt
    update-ca-certificates 2>/dev/null
    echo "doubleagent: CA installed (Debian/Ubuntu)"

elif [ -f /etc/alpine-release ]; then
    # Alpine
    cp "$CA_CERT" /usr/local/share/ca-certificates/doubleagent-ca.crt
    update-ca-certificates 2>/dev/null
    echo "doubleagent: CA installed (Alpine)"

elif [ -f /etc/redhat-release ] || [ -f /etc/centos-release ] || [ -f /etc/fedora-release ] || [ -d /etc/yum.repos.d ]; then
    # RHEL / CentOS / Fedora / Amazon Linux
    cp "$CA_CERT" /etc/pki/ca-trust/source/anchors/doubleagent-ca.crt
    update-ca-trust extract 2>/dev/null
    echo "doubleagent: CA installed (RHEL/CentOS/Fedora)"

elif [ -f /etc/SuSE-release ] || [ -f /etc/SUSE-brand ]; then
    # SUSE / openSUSE
    cp "$CA_CERT" /etc/pki/trust/anchors/doubleagent-ca.crt
    update-ca-certificates 2>/dev/null
    echo "doubleagent: CA installed (SUSE)"

else
    echo "doubleagent: unknown OS — attempting generic install"
    # Try the Debian/Alpine path as a best-effort fallback
    mkdir -p /usr/local/share/ca-certificates
    cp "$CA_CERT" /usr/local/share/ca-certificates/doubleagent-ca.crt
    if command -v update-ca-certificates >/dev/null 2>&1; then
        update-ca-certificates 2>/dev/null
        echo "doubleagent: CA installed (generic, update-ca-certificates)"
    elif command -v update-ca-trust >/dev/null 2>&1; then
        update-ca-trust extract 2>/dev/null
        echo "doubleagent: CA installed (generic, update-ca-trust)"
    else
        echo "doubleagent: WARNING — could not find update-ca-certificates or update-ca-trust."
        echo "doubleagent: The CA cert has been copied but may not be trusted by all tools."
        echo "doubleagent: Set NODE_EXTRA_CA_CERTS, REQUESTS_CA_BUNDLE, SSL_CERT_FILE manually."
    fi
fi

# Java support hint (requires keytool which is JDK-specific)
if command -v keytool >/dev/null 2>&1 && [ -n "$JAVA_HOME" ]; then
    CACERTS="$JAVA_HOME/lib/security/cacerts"
    if [ -f "$CACERTS" ]; then
        keytool -importcert -noprompt -keystore "$CACERTS" \
            -storepass changeit -alias doubleagent -file "$CA_CERT" 2>/dev/null || true
        echo "doubleagent: CA installed into Java truststore"
    fi
fi

echo "doubleagent: CA trust store updated successfully"
