#!/usr/bin/env python3
"""Protect the display's screen from burn-in: when nobody is there, show something that moves.

  nobody there for SAVER_MINUTES, room bright -> full-screen photo slideshow with a clock over it
  nobody there for SAVER_MINUTES, room dark   -> dim clock on black that shifts position
  someone appears, touches, speaks            -> the view it was on before

The screen is never turned off. Both faces are one view (/smart-display/saver, one card);
the card switches between them as input_boolean.kitchen_display_dark changes.

"Someone is there" is the display's own camera (VACA's motion detection,
binary_sensor.…_motion) plus anything that shows a person using it: a touch, the wake word,
the volume rocker, a change of view. All of those press one button helper, so "idle" is
simply "that button has not been pressed for a while and the camera sees nobody". In a dark
room the camera is ignored (noise in a dark picture reads as motion); touch and voice still count.

"Dark" comes from the display's ambient light sensor, reported by device/lightsense.sh to
the webhook kitchen_display_lux: dark below DARK_LUX, bright above BRIGHT_LUX, unchanged in
between. If no reading has arrived for LUX_STALE_MINUTES (reporter not installed, display
offline), the sun decides instead: dark when it is more than SUN_DARK_DEGREES below the horizon.

Creates (repeatable):
  - input_button.kitchen_display_activity      pressed on every sign of life
  - input_text.kitchen_display_saver_return    the view to go back to
  - input_number.kitchen_display_lux           last light reading
  - input_datetime.kitchen_display_lux_at      when it arrived
  - input_boolean.kitchen_display_dark         the room is dark
  - the dashboard resource ha/frontend/kitchen_saver.js (the card, touch reporting)
  - automations "Smart Display - Activity", "Smart Display - Screen saver", "Smart Display - Light level"
and turns on VACA's camera motion detection (MOTION_MODE, MOTION_SENSITIVITY).

The camera takeover (ha/camera_takeover.py) always wins: it navigates away, this automation
sees the view change and stands down. Do Not Disturb is not involved. The saver view itself
is part of the dashboard (ha/build_smart_display.py); photos come from ha/photo_album.py.
Brightness is left to the display's auto-brightness, which needs VACA to be allowed to
write system settings: adb shell appops set com.msp1974.vacompanion WRITE_SETTINGS allow

  $AVB_PYTHON ha/screen_saver.py            # install or update
  $AVB_PYTHON ha/screen_saver.py remove     # remove automations and the resource
"""
import asyncio, base64, json, pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ha_ws import call

SAVER_MINUTES = 5        # nobody there this long: show the saver
DARK_LUX = 3             # room light below this: dark clock
BRIGHT_LUX = 8           # room light above this: photo slideshow (in between: no change)
LUX_STALE_MINUTES = 15   # no light reading for this long: let the sun decide
SUN_DARK_DEGREES = -4    # sun elevation below this counts as dark when there is no reading
MOTION_MODE = "motion"   # VACA camera detection: "motion", "face" or "none"
MOTION_SENSITIVITY = 20  # 0-100. At VACA's default of 70 an empty, bright kitchen read as motion two or three times a minute

DEV = "vaca_ha0000xx"
DISPLAY = "sensor.den_display"
PRESENCE = f"binary_sensor.{DEV}_motion"
SATELLITE = f"assist_satellite.{DEV}"
BLACK = f"switch.{DEV}_screen_saver"        # VACA's own black overlay (not used here; cleared in case someone turned it on)
AUTO_BRIGHTNESS = f"switch.{DEV}_auto_brightness"
LUX = "input_number.kitchen_display_lux"
LUX_AT = "input_datetime.kitchen_display_lux_at"   # when that reading arrived (a restored number looks fresh after a restart)
DARK = "input_boolean.kitchen_display_dark"
LUX_WEBHOOK = "kitchen_display_lux"
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
    if LUX not in states:
        await call([{"type": "input_number/create", "name": "Kitchen display lux", "min": 0, "max": 100000,
                     "step": 1, "mode": "box", "unit_of_measurement": "lx", "icon": "mdi:brightness-5"}])
    if LUX_AT not in states:
        await call([{"type": "input_datetime/create", "name": "Kitchen display lux at", "has_date": True,
                     "has_time": True, "icon": "mdi:clock-check-outline"}])
    if DARK not in states:
        await call([{"type": "input_boolean/create", "name": "Kitchen display dark", "icon": "mdi:weather-night"}])


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
    "conditions": [
        {"condition": "template", "value_template": f"{{{{ trigger.id != 'view' or not ({ON_SAVER}) }}}}"},
        # Noise in a dark picture reads as motion, and nobody is looking at a display in a dark room.
        {"condition": "template", "value_template": f"{{{{ trigger.id != 'camera' or not is_state('{DARK}', 'on') }}}}"}],
    "actions": [{"action": "input_button.press", "target": {"entity_id": ACTIVITY}}],
    "mode": "single", "max_exceeded": "silent",
}

# Picking up a saver that is already showing needs no idle check; starting one does.
IDLE = ("{% if trigger.id == 'resume' %}" f"{{{{ {ON_SAVER} }}}}" "{% else %}"
        f"{{{{ (not is_state('{PRESENCE}', 'on') or is_state('{DARK}', 'on')) "
        f"and (now() - states.{ACTIVITY}.last_changed).total_seconds() >= {SAVER_MINUTES * 60 - 5} "
        f"and is_state('{SATELLITE}', 'idle') "
        f"and (state_attr('{DISPLAY}', 'mode') or 'normal') == 'normal' "
        f"and '{TAKEOVER}' not in {PATH} and '/view-assist/camera' not in {PATH} }}}}"
        "{% endif %}")
# Either somebody did something, or the display is no longer on the saver view (camera
# takeover, a timer ringing, a voice request that opened a view).
STOP = [{"trigger": "state", "entity_id": ACTIVITY},
        {"trigger": "template", "value_template": f"{{{{ not ({ON_SAVER}) }}}}"}]

saver = {
    "alias": "Smart Display - Screen saver",
    "description": f"Nobody at the kitchen display for {SAVER_MINUTES} minutes: photo slideshow with a clock, "
                   "or a dim clock when the room is dark. Presence, touch or voice brings back the previous view",
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
        # The saver has to be visible: VACA's black overlay off, backlight on automatic.
        {"action": "switch.turn_off", "target": {"entity_id": BLACK}},
        {"action": "switch.turn_on", "target": {"entity_id": AUTO_BRIGHTNESS}},
        {"wait_for_trigger": STOP},
        # Still on the saver: nothing else took the screen, so go back to where it was.
        {"if": [{"condition": "template", "value_template": f"{{{{ {ON_SAVER} }}}}"}],
         "then": [{"action": "view_assist.navigate",
                   "data": {"device": DISPLAY,
                            "path": f"{{% set p = states('{RETURN}') %}}"
                                    f"{{{{ p if p.startswith('/') and p != '{SAVER}' else '{HOME}' }}}}"}}]},
    ],
    "mode": "single", "max_exceeded": "silent",
}

# Dark or bright, with a gap between the two thresholds so it cannot flap around one value.
IS_DARK = (f"{{% set lux = states('{LUX}') | float(-1) %}}"
           f"{{% set fresh = lux >= 0 and now().timestamp() - (state_attr('{LUX_AT}', 'timestamp') or 0) < {LUX_STALE_MINUTES * 60} %}}"
           "{% if fresh %}"
           f"{{{{ lux < {DARK_LUX} or (lux <= {BRIGHT_LUX} and is_state('{DARK}', 'on')) }}}}"
           "{% else %}"
           f"{{{{ state_attr('sun.sun', 'elevation') | float(0) < {SUN_DARK_DEGREES} }}}}"
           "{% endif %}")
light = {
    "alias": "Smart Display - Light level",
    "description": f"Keeps 'Kitchen display dark' in step with the room: dark below {DARK_LUX} lx, bright above "
                   f"{BRIGHT_LUX} lx, by the display's own light sensor; by the sun when the sensor has not reported",
    "triggers": [
        {"trigger": "webhook", "id": "lux", "webhook_id": LUX_WEBHOOK, "allowed_methods": ["POST"], "local_only": True},
        {"trigger": "state", "entity_id": "sun.sun", "attribute": "elevation", "id": "sun"},
        {"trigger": "time_pattern", "minutes": "/5", "id": "tick"},
        {"trigger": "homeassistant", "event": "start", "id": "tick"},
    ],
    "actions": [
        {"if": [{"condition": "trigger", "id": "lux"}],
         "then": [{"action": "input_number.set_value", "target": {"entity_id": LUX},
                   "data": {"value": "{{ [[trigger.json.lux | float(0), 0] | max, 100000] | min }}"}},
                  {"action": "input_datetime.set_datetime", "target": {"entity_id": LUX_AT},
                   "data": {"timestamp": "{{ now().timestamp() }}"}}]},
        {"if": [{"condition": "template", "value_template": IS_DARK}],
         "then": [{"action": "input_boolean.turn_on", "target": {"entity_id": DARK}}],
         "else": [{"action": "input_boolean.turn_off", "target": {"entity_id": DARK}}]},
    ],
    "mode": "queued", "max": 5, "max_exceeded": "silent",
}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "remove":
        asyncio.run(resource(False))
        for a in ("smart_display_screen_saver", "smart_display_activity", "smart_display_light_level"):
            print(ha("DELETE", f"/api/config/automation/config/{a}"))
        print(ha("POST", "/api/services/select/select_option",
                 {"entity_id": f"select.{DEV}_motion_detection", "option": "none"}))
        return
    asyncio.run(helpers())
    asyncio.run(resource(True))
    print(ha("POST", "/api/services/select/select_option",
             {"entity_id": f"select.{DEV}_motion_detection", "option": MOTION_MODE}))
    print(ha("POST", "/api/services/number/set_value",
             {"entity_id": f"number.{DEV}_motion_detection_sensitivity", "value": MOTION_SENSITIVITY}))
    print(ha("POST", "/api/config/automation/config/smart_display_activity", activity))
    print(ha("POST", "/api/config/automation/config/smart_display_screen_saver", saver))
    print(ha("POST", "/api/config/automation/config/smart_display_light_level", light))


main()
