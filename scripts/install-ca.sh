#!/bin/sh
# install-ca.sh — Install the doubleagent CA certificate into the system trust
# store AND set runtime-specific environment variables (NODE_EXTRA_CA_CERTS,
# REQUESTS_CA_BUNDLE, SSL_CERT_FILE, CURL_CA_BUNDLE, GIT_SSL_CAINFO).
#
# Supports: Debian/Ubuntu, Alpine, RHEL/Fedora/CentOS, Amazon Linux, SUSE.
# Run this in the AI container's entrypoint before any network calls.
#
# The env vars are exported in the current shell (inherited by `exec`),
# written to /etc/environment, and to /etc/profile.d/doubleagent-ca.sh so
# they are available even when the process runs as a non-root user.
#
# Usage:
#   /certs/install-ca.sh [path-to-ca.crt]
#
# If no path is given, defaults to /certs/ca.crt.

set -e

CA_CERT="${1:-/certs/ca.crt}"

if [ ! -f "$CA_CERT" ]; then
    echo "doubleagent: CA cert not found at $CA_CERT — skipping install."
    echo "doubleagent: Neither the trust store nor certificate env vars will be configured."
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
        echo "doubleagent: The certificate env vars below will still be set."
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

# ---------------------------------------------------------------------------
# Set runtime-specific environment variables so tools that don't use the
# system trust store still pick up the CA cert (Node.js, Python requests,
# curl, git, generic OpenSSL).
#
# Three mechanisms are used so this works regardless of how the container
# starts the main process:
#
#   1. `export` in the current shell — inherited by `exec` in the same
#      entrypoint chain (covers the common case).
#   2. /etc/environment — read by PAM-based logins and some container
#      runtimes. Works for non-root users.
#   3. /etc/profile.d/doubleagent-ca.sh — sourced by login shells (bash,
#      sh, ash, zsh). Works when the process drops to another user.
#
# We only set a variable if it is not already set, so user overrides in
# the Compose environment section still take precedence.
# ---------------------------------------------------------------------------

mkdir -p /etc/profile.d

# Build the profile.d script from scratch (overwrite) so repeated
# container restarts never produce duplicate lines.
_DA_PROFILE="/etc/profile.d/doubleagent-ca.sh"
: > "$_DA_PROFILE"

# Strip any of our five variables from /etc/environment so we can
# re-append them cleanly. We don't need comment markers — the variable
# names themselves are the identifier. Using a temp file avoids the
# printf-on-empty-string pitfall that would inject a blank line.
_DA_VARS='^\(NODE_EXTRA_CA_CERTS\|REQUESTS_CA_BUNDLE\|SSL_CERT_FILE\|CURL_CA_BUNDLE\|GIT_SSL_CAINFO\)='
if [ -f /etc/environment ]; then
    grep -v "$_DA_VARS" /etc/environment > /etc/environment.tmp || true
    mv /etc/environment.tmp /etc/environment
fi

_da_set_var() {
    _name="$1"
    _value="$2"
    eval "_current=\${$_name:-}"
    if [ -z "$_current" ]; then
        export "$_name=$_value"
        echo "$_name=$_value" >> /etc/environment
        echo "export $_name=$_value" >> "$_DA_PROFILE"
    else
        echo "doubleagent: $_name already set — skipping"
    fi
}

_da_set_var NODE_EXTRA_CA_CERTS "$CA_CERT"
_da_set_var REQUESTS_CA_BUNDLE  "$CA_CERT"
_da_set_var SSL_CERT_FILE       "$CA_CERT"
_da_set_var CURL_CA_BUNDLE      "$CA_CERT"
_da_set_var GIT_SSL_CAINFO      "$CA_CERT"

chmod 644 /etc/environment
chmod 644 "$_DA_PROFILE"

echo "doubleagent: certificate environment variables configured"
echo "doubleagent: CA trust store updated successfully"
