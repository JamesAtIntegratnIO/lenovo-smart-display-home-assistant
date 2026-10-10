#!/usr/bin/env python3
"""Set up the photo source for the display's screen saver: one shared Google Photos album.

The album link is the single setting. Put it in ALBUM_URL below and rerun, or type it into
the helper "Kitchen display photo album link" in Home Assistant (Settings > Devices &
services > Helpers). While it is empty the slideshow shows placeholder photos.

What this does (repeatable):
  1. creates input_text.kitchen_display_album_url (anything but a Google Photos share link counts as empty);
  2. copies ha/album_sync.py to /config/kitchen_display/ on Home Assistant over SSH;
  3. writes /config/packages/kitchen_display.yaml: a command_line sensor
     (sensor.kitchen_display_album, state = number of photos) that runs the sync every
     REFRESH_HOURS hours. Needs `homeassistant: packages: !include_dir_named packages` in
     configuration.yaml, and one Home Assistant restart the first time;
  4. creates "Smart Display - Refresh photo album", which syncs at once when the link changes.

Needs SSH to the Terminal & SSH add-on (HA_SSH, default root@10.0.1.174). Run from the
project root with $AVB_PYTHON, like the other scripts in ha/.
"""
import json, os, pathlib, subprocess, sys

ALBUM_URL = ""          # e.g. "https://photos.app.goo.gl/…" ; empty leaves the helper as it is
REFRESH_HOURS = 6
HA_SSH = os.environ.get("HA_SSH", "root@10.0.1.174")
HELPER = "input_text.kitchen_display_album_url"
SENSOR = "sensor.kitchen_display_album"
# The link is passed to a shell command, so the command only ever gets a plain share link;
# anything else in the helper counts as empty. (A `pattern` on the helper itself left it
# unavailable after a Home Assistant restart, so the check lives in the command.)
SHARE_LINK = r"^https://(photos\.app\.goo\.gl|photos\.google\.com)/[A-Za-z0-9/_?=&.-]+$"

PACKAGE = f"""# Written by ha/photo_album.py (lenovo-smart-display). Photo source for the kitchen display's screen saver.
command_line:
  - sensor:
      name: Kitchen display album
      unique_id: kitchen_display_album
      icon: mdi:image-multiple
      command: >-
        python3 /config/kitchen_display/album_sync.py
        "{{% set u = states('{HELPER}') %}}{{{{ u if u is match('{SHARE_LINK}') else '' }}}}"
      command_timeout: 600
      scan_interval: {REFRESH_HOURS * 3600}
      value_template: "{{{{ value_json.count }}}}"
      json_attributes: [source, updated, error]
      unit_of_measurement: photos
"""


def run(args, **kw):
    r = subprocess.run(args, capture_output=True, text=True, **kw)
    if r.returncode:
        sys.exit(f"{' '.join(args[:3])}…: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def ha(method, path, body=None):
    args = [sys.executable, "ha/ha_rest.py", method, path] + ([json.dumps(body)] if body is not None else [])
    return subprocess.run(args, capture_output=True, text=True).stdout


def ws(msg):
    return subprocess.run([sys.executable, "ha/ha_ws.py", "call", json.dumps(msg)], capture_output=True, text=True).stdout


if '"http_error"' in ha("GET", f"/api/states/{HELPER}"):
    print(ws({"type": "input_text/create", "name": "Kitchen display album url", "max": 255, "icon": "mdi:image-album"}))
    print(ws({"type": "input_text/update", "input_text_id": "kitchen_display_album_url",
              "name": "Kitchen display photo album link", "max": 255, "icon": "mdi:image-album"}))
if ALBUM_URL:
    print(ha("POST", "/api/services/input_text/set_value", {"entity_id": HELPER, "value": ALBUM_URL}))

run(["ssh", HA_SSH, "mkdir -p /config/kitchen_display /config/packages /config/www/kitchen_display"])
run(["scp", "-q", "ha/album_sync.py", f"{HA_SSH}:/config/kitchen_display/album_sync.py"])
run(["ssh", HA_SSH, "cat > /config/packages/kitchen_display.yaml"], input=PACKAGE)
print("installed album_sync.py and packages/kitchen_display.yaml")

config = {"alias": "Smart Display - Refresh photo album",
          "description": "Fetch the shared Google Photos album for the kitchen display's screen saver as soon as its link changes",
          "triggers": [{"trigger": "state", "entity_id": HELPER}],
          "actions": [{"delay": {"seconds": 2}},
                      {"action": "homeassistant.update_entity", "target": {"entity_id": SENSOR}}],
          "mode": "restart"}
print(ha("POST", "/api/config/automation/config/smart_display_photo_album", config))

if '"http_error"' in ha("GET", f"/api/states/{SENSOR}"):
    print(f"{SENSOR} does not exist yet: check the configuration and restart Home Assistant once:\n"
          "  python3 ha/ha_rest.py POST /api/config/core/check_config\n"
          "  python3 ha/ha_rest.py POST /api/services/homeassistant/restart '{}'")
else:
    print(ha("POST", "/api/services/homeassistant/update_entity", {"entity_id": SENSOR}))
    print(ha("GET", f"/api/states/{SENSOR}"))
