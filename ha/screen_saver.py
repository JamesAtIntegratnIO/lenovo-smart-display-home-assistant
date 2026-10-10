#!/usr/bin/env python3
"""Protect the display's screen from burn-in: slideshow when nobody is there, then dark.

  nobody there for SAVER_MINUTES      -> full-screen photo slideshow (/smart-display/saver)
  slideshow up for OFF_MINUTES more   -> dim for DIM_SECONDS, then black with the backlight off
  someone appears, touches, speaks    -> backlight back, and the view it was on before

"Someone is there" is the display's own camera (VACA's motion detection,
binary_sensor.…_motion) plus anything that shows a person using it: a touch, the wake word,
the volume rocker, a change of view. All of those press one button helper, so "idle" is
simply "that button has not been pressed for a while and the camera sees nobody".

Creates (repeatable):
  - input_button.kitchen_display_activity      pressed on every sign of life
  - input_text.kitchen_display_saver_return    the view to go back to
  - the dashboard resource ha/frontend/kitchen_saver.js (slideshow card, touch reporting)
  - automation "Smart Display - Activity"
  - automation "Smart Display - Screen saver"
and turns on VACA's camera motion detection (MOTION_MODE).

The camera takeover (ha/camera_takeover.py) always wins: it navigates away, this automation
sees the view change, restores the backlight and stands down. Do Not Disturb is not involved.
The saver view itself is part of the dashboard (ha/build_smart_display.py); photos come from
ha/photo_album.py.

Dark means the backlight at 0 with the saver view still up underneath (the card stops
changing pictures), so a touch still lands on it and wakes the display. Android stays awake,
so the wake word keeps working. VACA can only move the backlight if it may write system
settings; once, on the display:
  adb shell appops set com.msp1974.vacompanion WRITE_SETTINGS allow

  $AVB_PYTHON ha/screen_saver.py            # install or update
  $AVB_PYTHON ha/screen_saver.py remove     # remove automations and the resource
"""
import asyncio, base64, json, pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ha_ws import call

SAVER_MINUTES = 5       # nobody there this long: start the slideshow
OFF_MINUTES = 30        # slideshow shown this long with still nobody there: go dark
DIM_SECONDS = 60        # dimmed slideshow before the backlight goes off
DIM_BRIGHTNESS = 5      # percent, during those seconds
AWAKE_BRIGHTNESS = 50   # percent, restored on wake before auto-brightness takes over again
MOTION_MODE = "motion"  # VACA camera detection: "motion", "face" or "none"

DEV = "vaca_ha0000xx"
DISPLAY = "sensor.den_display"
PRESENCE = f"binary_sensor.{DEV}_motion"
SATELLITE = f"assist_satellite.{DEV}"
BLACK = f"switch.{DEV}_screen_saver"        # VACA's own black overlay (not used here; cleared in case someone turned it on)
AUTO_BRIGHTNESS = f"switch.{DEV}_auto_brightness"
BRIGHTNESS = f"number.{DEV}_screen_brightness"
VOLUME = f"number.{DEV}_music_volume"
ACTIVITY = "input_button.kitchen_display_activity"
RETURN = "input_text.kitchen_display_saver_return"
SAVER = "/smart-display/saver"
HOME = "/smart-display/home"
TAKEOVER = "takeover=1"   # ha/camera_takeover.py's mark on its own camera view

MARK = "data:text/javascript;base64,"
JS = pathlib.Path(__file__).parent / "frontend" / "kitchen_saver.js"


def ha(method, path, body=None):
    args = [sys.executable, "ha/ha_rest.py", method, path] + ([json.dumps(body)] if body is not None else [])
    return subprocess.run(args, capture_output=True, text=True).stdout


def ours(res):
    if not res["url"].startswith(MARK):
        return False
    try:
        return b"__kitchenSaver" in base64.b64decode(res["url"][len(MARK):])
    except Exception:
        return False


async def resource(install):
    """Register the card as a `data:` URL resource, as ha/hls_guard.py does: nothing to copy to Home Assistant."""
    for r in (await call([{"type": "lovelace/resources"}]))[0]:
        if ours(r):
            await call([{"type": "lovelace/resources/delete", "resource_id": r["id"]}])
    if install:
        url = MARK + base64.b64encode(JS.read_bytes()).decode()
        await call([{"type": "lovelace/resources/create", "res_type": "module", "url": url}])


async def helpers():
    states = {s["entity_id"] for s in (await call([{"type": "get_states"}]))[0]}
    if ACTIVITY not in states:
        await call([{"type": "input_button/create", "name": "Kitchen display activity", "icon": "mdi:gesture-tap"}])
    if RETURN not in states:
        await call([{"type": "input_text/create", "name": "Kitchen display saver return", "max": 255,
                     "icon": "mdi:image-multiple"}])


PATH = f"(state_attr('{DISPLAY}', 'current_path') or '')"
ON_SAVER = f"{PATH} == '{SAVER}'"

activity = {
    "alias": "Smart Display - Activity",
    "description": "Presses the kitchen display's activity button whenever someone is seen at it or uses it. "
                   "The screen saver counts idle time from the last press",
    "triggers": [
        {"trigger": "state", "entity_id": PRESENCE, "to": "on", "id": "camera"},
        {"trigger": "state", "entity_id": SATELLITE, "id": "voice",
         "not_from": ["unavailable", "unknown"], "not_to": ["unavailable", "unknown"]},
        {"trigger": "state", "entity_id": VOLUME, "id": "volume",
         "not_from": ["unavailable", "unknown"], "not_to": ["unavailable", "unknown"]},
        # A tap on VACA's own black screen turns its switch off.
        {"trigger": "state", "entity_id": BLACK, "from": "on", "to": "off", "id": "tap"},
        {"trigger": "state", "entity_id": DISPLAY, "attribute": "current_path", "id": "view"},
    ],
    # Going to the saver view is not a sign of life (the saver does it itself, and so does a
    # camera takeover that started from the saver when it hands the screen back).
    "conditions": [{"condition": "template",
                    "value_template": f"{{{{ trigger.id != 'view' or not ({ON_SAVER}) }}}}"}],
    "actions": [{"action": "input_button.press", "target": {"entity_id": ACTIVITY}}],
    "mode": "single", "max_exceeded": "silent",
}

# Picking up a saver that is already showing needs no idle check; starting one does.
IDLE = ("{% if trigger.id == 'resume' %}" f"{{{{ {ON_SAVER} }}}}" "{% else %}"
        f"{{{{ not is_state('{PRESENCE}', 'on') "
        f"and (now() - states.{ACTIVITY}.last_changed).total_seconds() >= {SAVER_MINUTES * 60 - 5} "
        f"and is_state('{SATELLITE}', 'idle') "
        f"and (state_attr('{DISPLAY}', 'mode') or 'normal') == 'normal' "
        f"and '{TAKEOVER}' not in {PATH} and '/view-assist/camera' not in {PATH} }}}}"
        "{% endif %}")
# Either somebody did something, or the display is no longer on the saver view (camera
# takeover, a timer ringing, a voice request that opened a view).
STOP = [{"trigger": "state", "entity_id": ACTIVITY},
        {"trigger": "template", "value_template": f"{{{{ not ({ON_SAVER}) }}}}"}]
NOBODY = "{{ wait.trigger is none }}"

saver = {
    "alias": "Smart Display - Screen saver",
    "description": f"Nobody at the kitchen display for {SAVER_MINUTES} minutes: photo slideshow. "
                   f"Still nobody {OFF_MINUTES} minutes later: dim, then screen dark. "
                   "Presence, touch or voice brings back the previous view",
    "triggers": [
        {"trigger": "state", "entity_id": ACTIVITY, "for": {"minutes": SAVER_MINUTES}, "id": "idle"},
        {"trigger": "state", "entity_id": PRESENCE, "to": "off", "for": {"minutes": SAVER_MINUTES}, "id": "idle"},
        # Catches an idle moment the two above were blocked at.
        {"trigger": "time_pattern", "minutes": "/5", "id": "idle"},
        # Already on the saver view with this automation not running: Home Assistant restarted,
        # or a camera takeover handed the screen back to the saver. Pick it up from there.
        {"trigger": "template", "value_template": f"{{{{ {ON_SAVER} }}}}", "for": {"seconds": 5}, "id": "resume"},
        {"trigger": "homeassistant", "event": "start", "id": "resume"},
    ],
    "conditions": [{"condition": "template", "alias": "Nobody there, and nothing else has the screen", "value_template": IDLE}],
    "actions": [
        {"if": [{"condition": "template", "value_template": f"{{{{ not ({ON_SAVER}) }}}}"}],
         "then": [
             {"action": "input_text.set_value", "target": {"entity_id": RETURN},
              "data": {"value": f"{{{{ {PATH} or '{HOME}' }}}}"}}]},
        # revert_timeout 0: View Assist leaves this view alone instead of going home after its view
        # timeout. Sent even when the saver is already up, because a camera takeover that hands the
        # screen back to it does so with the normal timeout, and this cancels that.
        {"action": "view_assist.navigate", "data": {"device": DISPLAY, "path": SAVER, "revert_timeout": 0}},
        # A slideshow has to be visible, whatever state an interrupted run left behind.
        {"action": "switch.turn_off", "target": {"entity_id": BLACK}},
        {"action": "switch.turn_on", "target": {"entity_id": AUTO_BRIGHTNESS}},
        {"wait_for_trigger": STOP, "timeout": {"minutes": OFF_MINUTES}, "continue_on_timeout": True},
        {"if": [{"condition": "template", "value_template": NOBODY}],
         "then": [
             {"action": "switch.turn_off", "target": {"entity_id": AUTO_BRIGHTNESS}},
             {"action": "number.set_value", "target": {"entity_id": BRIGHTNESS}, "data": {"value": DIM_BRIGHTNESS}},
             {"wait_for_trigger": STOP, "timeout": {"seconds": DIM_SECONDS}, "continue_on_timeout": True},
             {"if": [{"condition": "template", "value_template": NOBODY}],
              "then": [
                  # Backlight off. VACA's black screen is not used for this: it holds the backlight at 2 of 255.
                  {"action": "number.set_value", "target": {"entity_id": BRIGHTNESS}, "data": {"value": 0}},
                  {"wait_for_trigger": STOP}]}]},
        # Wake. Backlight first, so whatever took the screen is visible at once.
        {"action": "number.set_value", "target": {"entity_id": BRIGHTNESS}, "data": {"value": AWAKE_BRIGHTNESS}},
        {"action": "switch.turn_on", "target": {"entity_id": AUTO_BRIGHTNESS}},
        {"action": "switch.turn_off", "target": {"entity_id": BLACK}},
        # Still on the saver: nothing else took the screen, so go back to where it was.
        {"if": [{"condition": "template", "value_template": f"{{{{ {ON_SAVER} }}}}"}],
         "then": [{"action": "view_assist.navigate",
                   "data": {"device": DISPLAY,
                            "path": f"{{% set p = states('{RETURN}') %}}"
                                    f"{{{{ p if p.startswith('/') and p != '{SAVER}' else '{HOME}' }}}}"}}]},
    ],
    "mode": "single", "max_exceeded": "silent",
}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "remove":
        asyncio.run(resource(False))
        for a in ("smart_display_screen_saver", "smart_display_activity"):
            print(ha("DELETE", f"/api/config/automation/config/{a}"))
        print(ha("POST", "/api/services/select/select_option",
                 {"entity_id": f"select.{DEV}_motion_detection", "option": "none"}))
        return
    asyncio.run(helpers())
    asyncio.run(resource(True))
    print(ha("POST", "/api/services/select/select_option",
             {"entity_id": f"select.{DEV}_motion_detection", "option": MOTION_MODE}))
    print(ha("POST", "/api/config/automation/config/smart_display_activity", activity))
    print(ha("POST", "/api/config/automation/config/smart_display_screen_saver", saver))


main()
