#!/usr/bin/env python3
"""Create the automation that puts a camera on the Smart Display when something happens there.

A person or vehicle detection on a UniFi Protect camera, or a ring of the doorbell, switches
the display to that camera's full-screen live view (/smart-display/cam-<name>, an Advanced
Camera Card built by ha/build_smart_display.py). When the camera has been quiet for CLEAR_SECONDS the
display goes back to the view it was on. Raw motion is not a trigger: trees and shadows
would take the screen over all day.

One person out front trips three cameras in turn, so a showing takeover is not replaced by
another camera: only the doorbell (its camera, or a ring) may take the screen from another
camera, and for COOLDOWN_SECONDS after a takeover starts the other cameras cannot start one.

"The view it was on" is the display's own report of its page (REAL, from the companion app).
View Assist's current_path only follows view_assist.navigate, so it misses every tab opened
by touch and would send the display back to the wrong one.

Needs one helper to remember where to go back to: input_text.den_display_takeover_return
(created here if missing). Run from the project root, like the other scripts in ha/.
"""
import json, subprocess, sys

DISPLAY = "sensor.den_display"
REAL = "sensor.vaca_ha0000xx_current_path"   # the page the display is really on, taps included
HOME = "/smart-display/home"
RETURN_HELPER = "input_text.den_display_takeover_return"
CLEAR_SECONDS = 30     # quiet time on the camera before the display goes back
MAX_SECONDS = 300      # give the screen back after this long even if detections keep coming
RING_HOLD_SECONDS = 30 # after a doorbell ring, other cameras cannot take the screen for this long
COOLDOWN_SECONDS = 120 # after a takeover starts, cameras other than the doorbell cannot start another for this long
DOORBELL_RING = "event.g4_doorbell_pro_poe_doorbell"
MARK = "takeover=1"    # in the path, so the automation can tell its own camera view from one asked for by voice

VIEWS = {  # camera -> its full-screen view; the names are the slugs in ha/build_smart_display.py CAMERAS
    "camera.front_doorbell_medium_resolution_channel": "/smart-display/cam-doorbell",
    "camera.front_driveway_medium_resolution_channel": "/smart-display/cam-driveway",
    "camera.front_landscape_medium_resolution_channel": "/smart-display/cam-landscape",
    "camera.back_yard_medium_resolution_channel": "/smart-display/cam-back-yard",
}
CAMERAS = {  # medium stream (the display decodes at most 1080p) -> detection sensors that trigger it
    "camera.front_doorbell_medium_resolution_channel": [
        "binary_sensor.g4_doorbell_pro_poe_person_detected",
        "binary_sensor.g4_doorbell_pro_poe_vehicle_detected"],
    "camera.front_driveway_medium_resolution_channel": [
        "binary_sensor.g6_bullet_person_detected_2",
        "binary_sensor.g6_bullet_vehicle_detected_2"],
    "camera.front_landscape_medium_resolution_channel": [
        "binary_sensor.g6_bullet_person_detected",
        "binary_sensor.g6_bullet_vehicle_detected"],
    "camera.back_yard_medium_resolution_channel": [
        "binary_sensor.back_yard_person_detected"],   # vehicle detection is off on this camera
}
DOORBELL_CAMERA = next(iter(CAMERAS))


def ha(method, path, body=None):
    args = [sys.executable, "ha/ha_rest.py", method, path] + ([json.dumps(body)] if body is not None else [])
    return subprocess.run(args, capture_output=True, text=True).stdout


if '"http_error"' in ha("GET", f"/api/states/{RETURN_HELPER}"):
    # Created under the display's first name so the entity id stays input_text.den_display_takeover_return
    # (the display moved to the kitchen; ids were kept), then given the name people see.
    for msg in ({"type": "input_text/create", "name": "Den display takeover return", "max": 255, "icon": "mdi:cctv"},
                {"type": "input_text/update", "input_text_id": "den_display_takeover_return",
                 "name": "Kitchen display takeover return", "max": 255, "icon": "mdi:cctv"}):
        print(subprocess.run([sys.executable, "ha/ha_ws.py", "call", json.dumps(msg)], capture_output=True, text=True).stdout)

triggers = [{"trigger": "state", "entity_id": DOORBELL_RING, "id": DOORBELL_CAMERA,
             "not_from": ["unavailable"], "not_to": ["unavailable", "unknown"]}]
for camera, sensors in CAMERAS.items():
    triggers.append({"trigger": "state", "entity_id": sensors, "from": "off", "to": "on", "id": camera})

RING_AGE = f"(now() - states.{DOORBELL_RING}.last_changed).total_seconds()"
ATTR_PATH = f"(state_attr('{DISPLAY}', 'current_path') or '')"
# A takeover is on the screen: View Assist's path carries the mark and the display is on a camera view.
# (The mark alone is not enough: it stays behind when someone taps away from the picture.)
SHOWING = f"('{MARK}' in {ATTR_PATH} and states('{REAL}') in {sorted(VIEWS.values())})"
SINCE_LAST = "(now() - (this.attributes.last_triggered or (0 | as_datetime))).total_seconds()"
conditions = [
    {"condition": "template", "alias": "Display is not on Do Not Disturb",
     "value_template": f"{{{{ state_attr('{DISPLAY}', 'do_not_disturb') != 'on' }}}}"},
    # The event entity's state is the time of the last ring. A reload restores an old one; that is not a ring.
    {"condition": "template", "alias": "A ring is a fresh one",
     "value_template": f"{{{{ trigger.entity_id != '{DOORBELL_RING}' "
                       "or (now() - (trigger.to_state.state | as_datetime)).total_seconds() | abs < 30 }}"},
    {"condition": "template", "alias": "A doorbell ring keeps the screen for a while",
     "value_template": f"{{{{ trigger.entity_id == '{DOORBELL_RING}' or trigger.id == '{DOORBELL_CAMERA}' "
                       f"or {RING_AGE} > {RING_HOLD_SECONDS} }}}}"},
    {"condition": "template", "alias": "Cameras do not take the screen from each other; only the doorbell does",
     "value_template": f"{{% if trigger.entity_id == '{DOORBELL_RING}' %}}true"
                       f"{{% elif trigger.id == '{DOORBELL_CAMERA}' %}}"
                       f"{{{{ not ({SHOWING} and states('{REAL}') == '{VIEWS[DOORBELL_CAMERA]}') }}}}"
                       f"{{% else %}}{{{{ not {SHOWING} and {SINCE_LAST} > {COOLDOWN_SECONDS} }}}}{{% endif %}}"},
]

DONE = ("{% set ns = namespace(last=started | as_datetime, on=false) %}"
        "{% for s in sensors[camera] %}"
        "{% if is_state(s, 'on') %}{% set ns.on = true %}{% endif %}"
        "{% if states[s] and states[s].last_changed > ns.last %}{% set ns.last = states[s].last_changed %}{% endif %}"
        "{% endfor %}"
        f"{{{{ (not ns.on and (now() - ns.last).total_seconds() >= {CLEAR_SECONDS}) "
        f"or (now() - (started | as_datetime)).total_seconds() >= {MAX_SECONDS} }}}}")
# Someone moved the display: by voice or an automation (View Assist's path loses the mark), or by
# touch (only the display's own path changes; it gets a few seconds to report the camera view first).
ON_CAMERA = f"('{MARK}' in {ATTR_PATH} and states('{REAL}') == views[camera])"
LEFT = (f"{{{{ '{MARK}' not in {ATTR_PATH} "
        f"or ((now() - (started | as_datetime)).total_seconds() > 10 and states('{REAL}') != views[camera]) }}}}")

actions = [
    {"variables": {
        "camera": "{{ trigger.id }}",
        "sensors": CAMERAS,
        "views": VIEWS,
        "started": "{{ now().isoformat() }}",
        # Already showing a takeover (this run restarted an earlier one): keep the first return point.
        "came_from": f"{{% set real = states('{REAL}') %}}"
                     f"{{% if {SHOWING} and '|' in states('{RETURN_HELPER}') %}}"
                     f"{{{{ states('{RETURN_HELPER}') }}}}"
                     f"{{% else %}}{{{{ state_attr('{DISPLAY}', 'mode') or 'normal' }}}}|"
                     # A View Assist answer view is not a place to return to; it would have gone home anyway.
                     f"{{{{ real if real.startswith('/smart-display/') else '{HOME}' }}}}{{% endif %}}"}},
    {"action": "input_text.set_value", "target": {"entity_id": RETURN_HELPER}, "data": {"value": "{{ came_from }}"}},
    # revert_timeout 0: View Assist leaves the view alone, so the camera holds the screen until this
    # automation gives it back. The mode is not touched (View Assist's own camera screen set "hold").
    {"action": "view_assist.navigate",
     "data": {"device": DISPLAY, "path": f"{{{{ views[camera] }}}}?{MARK}", "revert_timeout": 0}},
    # Poll until the camera has been quiet long enough, or someone moves the display elsewhere.
    {"repeat": {
        "sequence": [{"delay": {"seconds": 3}}],
        "until": [{"condition": "or", "conditions": [
            {"condition": "template", "value_template": DONE},
            {"condition": "template", "value_template": LEFT}]}]}},
    # Still on the camera: go back to where the display was. revert_timeout 0 again, or View Assist
    # would send any view but its home screen home after its view timeout.
    {"if": [{"condition": "template", "value_template": f"{{{{ {ON_CAMERA} }}}}"}],
     "then": [{"action": "view_assist.navigate",
               "data": {"device": DISPLAY, "path": "{{ came_from.split('|', 1)[1] }}", "revert_timeout": 0}}],
     # Someone moved the display by touch (a tap on the picture opens the camera grid): they stay
     # where they are. Navigating to that same view only tells View Assist, whose path still
     # carries the mark, where the display really is.
     "else": [{"if": [{"condition": "template",
                       "value_template": f"{{{{ '{MARK}' in {ATTR_PATH} and states('{REAL}').startswith('/smart-display/') }}}}"}],
               "then": [{"action": "view_assist.navigate",
                         "data": {"device": DISPLAY, "path": f"{{{{ states('{REAL}') }}}}", "revert_timeout": 0}}]}]},
]

config = {"alias": "Smart Display - Show camera on detection or doorbell",
          "description": "Person or vehicle on a camera, or a doorbell ring, shows that camera on the Kitchen display, "
                         f"then returns to the view it was on {CLEAR_SECONDS} seconds after it clears. "
                         "Only the doorbell takes the screen from another camera",
          "triggers": triggers, "conditions": conditions, "actions": actions, "mode": "restart"}
print(ha("POST", "/api/config/automation/config/smart_display_camera_takeover", config))
