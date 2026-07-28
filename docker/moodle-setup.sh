#!/bin/bash
set -euo pipefail

moodle_user="${DEMO_MOODLE_USER:-daemon}"
if [[ -d /bitnami/moodledata ]]; then
  chown -R "$(id -u "$moodle_user"):$(id -g "$moodle_user")" /bitnami/moodledata
fi

exec /opt/bitnami/scripts/moodle/setup-bitnami.sh "$@"
