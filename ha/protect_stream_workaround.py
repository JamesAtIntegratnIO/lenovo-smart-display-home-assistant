#!/usr/bin/env python3
"""Temporary workaround for Home Assistant 2026.10.0 marking UniFi Protect cameras unavailable.

2026.10.0 moved to FFmpeg 9, which verifies TLS certificates by default. Protect serves RTSPS
with a self-signed certificate, so Home Assistant's HLS stream worker fails ("Error opening
stream (I/O error, rtsps://...)") every time a camera is opened live, and the camera entity
flaps to unavailable until the integration is reloaded. WebRTC on the display is not affected.
Upstream: home-assistant/core issue 184775, fixed in 2026.10.1 (PRs 184877 and 184930).

Until that update is installed, this automation reloads the Protect integration shortly after
a camera drops, once the display is no longer showing a live camera.
After updating to 2026.10.1 or later, delete the automation; it is not needed.
"""
import json, subprocess, sys

DISPLAY = "sensor.den_display"
CAMERAS = [
    "camera.front_doorbell_medium_resolution_channel",
    "camera.front_driveway_medium_resolution_channel",
    "camera.front_landscape_medium_resolution_channel",
    "camera.back_yard_medium_resolution_channel",
]
NOT_ON_CAMERA = f"{{{{ '/view-assist/camera' not in (state_attr('{DISPLAY}', 'current_path') or '') }}}}"

config = {
    "alias": "Smart Display - Reload Protect when a camera drops (temporary, HA 2026.10.0)",
    "description": "Workaround for home-assistant/core issue 184775. Delete after updating to 2026.10.1 or later.",
    "triggers": [{"trigger": "state", "entity_id": CAMERAS, "to": "unavailable"}],
    "actions": [
        {"delay": {"seconds": 20}},
        # A reload would cut a live picture, so wait until the display has left the camera view.
        {"wait_template": NOT_ON_CAMERA, "timeout": {"minutes": 6}},
        {"delay": {"seconds": 5}},
        {"condition": "template", "alias": "Still unavailable",
         "value_template": "{{ expand(cameras) | selectattr('state', 'eq', 'unavailable') | list | count > 0 }}"},
        {"action": "homeassistant.reload_config_entry", "target": {"entity_id": CAMERAS[0]}},
        # The reload itself makes every camera unavailable for a moment; single mode ignores that.
        {"delay": {"seconds": 60}},
    ],
    "variables": {"cameras": CAMERAS},
    "mode": "single", "max_exceeded": "silent"}
print(subprocess.run([sys.executable, "ha/ha_rest.py", "POST",
                      "/api/config/automation/config/smart_display_protect_stream_workaround", json.dumps(config)],
                     capture_output=True, text=True).stdout)
