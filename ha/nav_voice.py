#!/usr/bin/env python3
"""Create the voice automation that jumps between Smart Display dashboard views."""
import json, subprocess, sys

DEVICE = "{{ view_assist_entity(trigger.device_id) or 'sensor.den_display' }}"
GO = "(go [back] [to] | return to | take me [to] | show [me] | open | pull up)"
VIEWS = {  # view path -> (spoken reply, phrases)
    "home": ("Home screen", [f"{GO} [the | my] (home | main) [(screen | page | view | dashboard)]", "go home"]),
    "lights": ("Lights", [f"{GO} [the | my] (lights | light controls | light switches) [(screen | page | view)]"]),
    "outside": ("Outside", [f"{GO} [the | my] (outside | outdoor | exterior | roof) [lights] (screen | page | view | controls)"]),
    "media": ("Media", [f"{GO} [the | my] (media | tv | television) (screen | page | view | controls)"]),
    "sports": ("Sports", [f"{GO} [the | my] sports (screen | page | view)"]),
}
triggers = [{"trigger": "conversation", "id": path, "command": cmds} for path, (_, cmds) in VIEWS.items()]
choices = [{"conditions": [{"condition": "trigger", "id": path}], "sequence": [
    # revert_timeout 0: the view stays until someone moves on. Without it View Assist sends any view
    # but its home screen home after its view timeout (20 s).
    {"action": "view_assist.navigate", "data": {"device": DEVICE, "path": f"/smart-display/{path}", "revert_timeout": 0}},
    {"set_conversation_response": reply}]} for path, (reply, _) in VIEWS.items()]
config = {"alias": "Smart Display - Go to a view by voice",
          "description": "Jump to a Smart Display dashboard view on the display that heard the request",
          "triggers": triggers, "actions": [{"choose": choices}], "mode": "restart"}
print(subprocess.run([sys.executable, "ha/ha_rest.py", "POST",
                      "/api/config/automation/config/smart_display_go_to_view", json.dumps(config)],
                     capture_output=True, text=True).stdout)
