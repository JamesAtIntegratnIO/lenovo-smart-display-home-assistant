#!/usr/bin/env python3
"""Create the voice automation that shows cameras on the Smart Display.

View Assist's own camera blueprint needs the word "camera" in the phrase and a single
wildcard for the name; a bare wildcard would also swallow "show me my timers". This
lists each camera's spoken names explicitly instead, so "show me the front driveway" works.
"""
import json, subprocess, sys

CAMERAS = {  # entity (medium stream: the display decodes at most 1080p) -> (label, spoken names)
    "camera.front_doorbell_medium_resolution_channel": ("doorbell", "(doorbell | front door | front doorbell | porch | front porch)"),
    "camera.front_driveway_medium_resolution_channel": ("driveway", "[front] (driveway | drive way)"),
    "camera.front_landscape_medium_resolution_channel": ("front yard", "[front] (landscape | yard | lawn)"),
    "camera.back_yard_medium_resolution_channel": ("back yard", "(back yard | backyard | back lawn | patio)"),
}
VERB = "(show | display | pull up | open) [me]"
NOUN = "(camera | cameras | cam | view | feed)"
DEVICE = "{{ view_assist_entity(trigger.device_id) or 'sensor.den_display' }}"

triggers = [{"trigger": "conversation", "id": "all", "command": [
    f"{VERB} [all] [the | my] (cameras | cams | camera feeds | security cameras)",
    f"{VERB} all [the | my] {NOUN}",
]}]
choices = [{"conditions": [{"condition": "trigger", "id": "all"}], "sequence": [
    {"action": "view_assist.navigate", "data": {"device": DEVICE, "path": "/smart-display/cameras"}},
    {"set_conversation_response": "Showing all cameras"}]}]
for entity, (label, names) in CAMERAS.items():
    triggers.append({"trigger": "conversation", "id": entity, "command": [f"{VERB} [the | my] {names} [{NOUN}]"]})
    choices.append({"conditions": [{"condition": "trigger", "id": entity}], "sequence": [
        {"action": "view_assist.navigate",
         "data": {"device": DEVICE, "path": f"/view-assist/camera?camera={entity}&timeout=120"}},
        {"set_conversation_response": f"Showing the {label} camera"}]})

config = {"alias": "Smart Display - Show cameras by voice",
          "description": "Show all cameras or one camera by name on the display that heard the request",
          "triggers": triggers, "actions": [{"choose": choices}], "mode": "restart"}
print(subprocess.run([sys.executable, "ha/ha_rest.py", "POST",
                      "/api/config/automation/config/smart_display_show_cameras", json.dumps(config)],
                     capture_output=True, text=True).stdout)
