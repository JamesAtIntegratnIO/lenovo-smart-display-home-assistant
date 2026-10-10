#!/usr/bin/env bash
# Install ha/themes/*.yaml into Home Assistant and make "Storm at Sea" the default dark theme.
# Needs SSH to the Terminal & SSH add-on (HA_SSH, default root@10.0.1.174) and ~/.hass_token.
# The built-in theme stays selectable (Profile > Theme > Home Assistant). To go back for everyone:
#   ha/ha_rest.py POST /api/services/frontend/set_theme '{"name":"default","mode":"dark"}'
set -euo pipefail
cd "$(dirname "$0")"
HA_SSH="${HA_SSH:-root@10.0.1.174}"
THEME="${1:-Storm at Sea}"

ssh "$HA_SSH" 'mkdir -p /config/themes'
scp themes/*.yaml "$HA_SSH:/config/themes/"
# Home Assistant only reads /config/themes if configuration.yaml says so.
ssh "$HA_SSH" '
  cd /config
  if grep -q "include_dir_merge_named themes" configuration.yaml; then
    echo "configuration.yaml already loads themes/"
  elif grep -q "^frontend:" configuration.yaml; then
    echo "configuration.yaml has a frontend: block without themes. Add this line under it, then rerun:"
    echo "  themes: !include_dir_merge_named themes"; exit 1
  else
    cp configuration.yaml configuration.yaml.bak-themes
    printf "\nfrontend:\n  themes: !include_dir_merge_named themes\n" >> configuration.yaml
    echo "added frontend themes include (backup: configuration.yaml.bak-themes)"
  fi'
python3 ha_rest.py POST /api/services/frontend/reload_themes '{}' >/dev/null
python3 ha_rest.py POST /api/services/frontend/set_theme "{\"name\":\"$THEME\",\"mode\":\"dark\"}" >/dev/null
echo "installed; \"$THEME\" is now the default dark theme"
