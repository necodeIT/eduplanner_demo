#!/bin/bash
set -euo pipefail

if [[ -z "${DEMO_BASE_URL:-}" ]]; then
  echo "DEMO_BASE_URL is required (for example http://localhost:420)" >&2
  exit 1
fi
if [[ "$DEMO_BASE_URL" =~ ^https://[^/?#@]+$ ]]; then
  export MOODLE_REVERSEPROXY="yes"
  export MOODLE_SSLPROXY="yes"
elif [[ "$DEMO_BASE_URL" =~ ^http://(localhost|127\.0\.0\.1)(:[0-9]+)?$ ]]; then
  export MOODLE_REVERSEPROXY="no"
  export MOODLE_SSLPROXY="no"
else
  echo "DEMO_BASE_URL must be an HTTPS origin or an HTTP localhost/127.0.0.1 origin without a path" >&2
  exit 1
fi

export MOODLE_HOST="${DEMO_BASE_URL#*://}"

mkdir -p /run/eduplanner-demo /var/lib/eduplanner-demo

# Local development checkouts can use restrictive umasks. Moodle plugins must
# remain readable by Bitnami's daemon user, including before post-init runs.
for plugin_dir in \
  /bitnami/moodle/local/lbplanner \
  /bitnami/moodle/local/modcustomfields \
  /bitnami/moodle/local/edudemo \
  /bitnami/moodle/auth/edudemo; do
  if [[ -d "$plugin_dir" ]]; then
    find "$plugin_dir" -type d -exec chmod 0755 {} +
    find "$plugin_dir" -type f -exec chmod 0644 {} +
  fi
done

# Bitnami may create cache entries as root during a fresh installation. Fix the
# named volume before its daemon-owned upgrade and Apache processes use it.
if [[ -d /bitnami/moodledata ]]; then
  chown -R "$(id -u daemon):$(id -g daemon)" /bitnami/moodledata
fi

exec /opt/bitnami/scripts/moodle/entrypoint.sh "$@"
