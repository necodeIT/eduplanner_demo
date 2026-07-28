#!/bin/bash
set -euo pipefail

sync_plugin() {
  local source="$1"
  local destination="$2"
  mkdir -p "$destination"
  rsync -a --delete "$source/" "$destination/"
}

sync_plugin /opt/eduplanner-demo/plugins/lbplanner /bitnami/moodle/local/lbplanner
sync_plugin /opt/eduplanner-demo/plugins/modcustomfields /bitnami/moodle/local/modcustomfields
sync_plugin /opt/eduplanner-demo/moodle-plugins/auth_edudemo /bitnami/moodle/auth/edudemo
sync_plugin /opt/eduplanner-demo/moodle-plugins/local_edudemo /bitnami/moodle/local/edudemo

config_php=/bitnami/moodle/config.php
if [[ ! -f "$config_php" ]]; then
  echo "Bitnami setup completed without creating $config_php" >&2
  exit 1
fi
owner_uid="$(id -u "${DEMO_MOODLE_USER:-daemon}")"
moodle_group="$(id -g "${DEMO_MOODLE_USER:-daemon}")"
chown -R "$owner_uid:$moodle_group" /bitnami/moodledata
chown -R "0:$moodle_group" /var/lib/eduplanner-demo
chmod -R g+rwX /var/lib/eduplanner-demo
chmod g+s /var/lib/eduplanner-demo
gosu "$owner_uid:$moodle_group" php /bitnami/moodle/admin/cli/upgrade.php --non-interactive
demo apply --bootstrap-only

if ! demo apply; then
  echo "Initial demo population failed; Moodle will start in degraded mode." >&2
fi

demo watch &
