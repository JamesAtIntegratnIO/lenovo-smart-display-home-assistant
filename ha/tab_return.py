#!/usr/bin/env python3
"""Create the automation that puts the Smart Display back on its tab after a voice answer.

A spoken answer, a timer or an alarm opens one of View Assist's own views (/view-assist/info,
/view-assist/alarm, ...). When View Assist is done with it, it goes to its home screen, whatever
tab the display was on. This remembers that tab and goes back to it instead.

The tab is read from the display's own report of its page (REAL): View Assist's current_path
only follows view_assist.navigate and never sees a tab opened by touch. The screen saver and the
camera takeover keep their own return points (ha/screen_saver.py, ha/camera_takeover.py).
Run from the project root, like the other scripts in ha/.
"""
import json, subprocess, sys

DISPLAY = "sensor.den_display"
REAL = "sensor.vaca_ha0000xx_current_path"   # the page the display is really on, taps included
HOME = "/smart-display/home"
SAVER = "/smart-display/saver"
TAKEOVER = "automation.smart_display_show_camera_on_detection_or_doorbell"
WAIT_MINUTES = 15   # an answer view open longer than this (a ringing alarm nobody stops) is forgotten

ANSWER = "/view-assist/"
config = {
    "alias": "Smart Display - Back to the tab after a voice answer",
    "description": "When a View Assist answer view closes and the Kitchen display goes to its home screen, "
                   "returns it to the tab it was on before the answer",
    "triggers": [{"trigger": "state", "entity_id": REAL}],
    "conditions": [
        {"condition": "template", "alias": "An answer view opened over a tab other than home",
         "value_template": f"{{{{ trigger.to_state.state.startswith('{ANSWER}') "
                           f"and trigger.from_state.state.startswith('/smart-display/') "
                           f"and trigger.from_state.state not in ['{HOME}', '{SAVER}'] }}}}"},
        # A camera view the takeover put up is its to hand back, not a tab.
        {"condition": "template", "alias": "No camera takeover is running",
         "value_template": f"{{{{ (state_attr('{TAKEOVER}', 'current') or 0) == 0 }}}}"},
    ],
    "actions": [
        {"variables": {"tab": "{{ trigger.from_state.state }}"}},
        {"wait_for_trigger": [{"trigger": "template",
                               "value_template": f"{{{{ not states('{REAL}').startswith('{ANSWER}') }}}}"}],
         "timeout": {"minutes": WAIT_MINUTES}, "continue_on_timeout": False},
        # Only View Assist's own return home is undone. A voice request for another view lands elsewhere.
        {"condition": "template",
         "value_template": f"{{{{ states('{REAL}') == '{HOME}' and state_attr('{DISPLAY}', 'current_path') == '{HOME}' }}}}"},
        # revert_timeout 0: or View Assist would send it home again after its view timeout.
        {"action": "view_assist.navigate", "data": {"device": DISPLAY, "path": "{{ tab }}", "revert_timeout": 0}},
    ],
    "mode": "single", "max_exceeded": "silent",
}
print(subprocess.run([sys.executable, "ha/ha_rest.py", "POST",
                      "/api/config/automation/config/smart_display_tab_return", json.dumps(config)],
                     capture_output=True, text=True).stdout)
