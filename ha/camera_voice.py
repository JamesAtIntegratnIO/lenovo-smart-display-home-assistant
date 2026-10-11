#!/usr/bin/env python3
"""Create the voice automation that shows cameras on the Smart Display.

View Assist's own camera blueprint needs the word "camera" in the phrase and a single
wildcard for the name; a bare wildcard would also swallow "show me my timers". This
lists each camera's spoken names explicitly instead, so "show me the front driveway" works.
"""
import json, subprocess, sys

CAMERAS = {  # full-screen view (the slugs in ha/build_smart_display.py CAMERAS) -> (label, spoken names)
    "/smart-display/cam-doorbell": ("doorbell", "(doorbell | front door | front doorbell | porch | front porch)"),
    "/smart-display/cam-driveway": ("driveway", "[front] (driveway | drive way)"),
    "/smart-display/cam-landscape": ("front yard", "[front] (landscape | yard | lawn)"),
    "/smart-display/cam-back-yard": ("back yard", "(back yard | backyard | back lawn | patio)"),
}
SHOW_SECONDS = 120  # how long a camera asked for by voice stays up before the display goes home
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
for view, (label, names) in CAMERAS.items():
    triggers.append({"trigger": "conversation", "id": view, "command": [f"{VERB} [the | my] {names} [{NOUN}]"]})
    choices.append({"conditions": [{"condition": "trigger", "id": view}], "sequence": [
        {"action": "view_assist.navigate", "data": {"device": DEVICE, "path": view, "revert_timeout": SHOW_SECONDS}},
        {"set_conversation_response": f"Showing the {label} camera"}]})

config = {"alias": "Smart Display - Show cameras by voice",
          "description": "Show all cameras or one camera by name on the display that heard the request",
          "triggers": triggers, "actions": [{"choose": choices}], "mode": "restart"}
print(subprocess.run([sys.executable, "ha/ha_rest.py", "POST",
                      "/api/config/automation/config/smart_display_show_cameras", json.dumps(config)],
                     capture_output=True, text=True).stdout)
