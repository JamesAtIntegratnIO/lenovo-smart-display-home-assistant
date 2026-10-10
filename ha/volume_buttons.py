#!/usr/bin/env python3
"""Create the Home Assistant automation behind the display's physical volume buttons.

A watcher on the display (device/volkeys.sh) POSTs a local webhook on each press. The
rocker is a whole-system volume: one level drives every sound the display makes.

  music + everything on the media stream  number.…_music_volume  (Android STREAM_MUSIC, via LEVELS)
  spoken replies and the wake chime        number.…_voice_volume  (0..7)
  timers and alarms                        number.…_alarm_volume  (0..100, floored so they stay audible)

The Music Assistant player's own gain is pinned at 100% so it never caps the system level.
"""
import json, subprocess, sys

DEV = "vaca_ha0000xx"
MASTER = f"number.{DEV}_music_volume"
VOICE = f"number.{DEV}_voice_volume"
ALARM = f"number.{DEV}_alarm_volume"
PLAYER = f"media_player.{DEV}_media_player_2"
# The display's Android volume curve is steep and mostly inaudible at the bottom
# (index 50 is -21 dB, index 30 is -33 dB), so equal index steps feel wrong. These eleven
# positions are 3 dB apart from -27 dB to full, read off the device's own curve
# (`dumpsys media.audio_policy`): each press is the same perceived change.
LEVELS = [0, 40, 45, 50, 55, 60, 68, 76, 84, 92, 100]
ALARM_FLOOR = 60   # alarms never go quieter than this (-15 dB)

# Find the position nearest the current volume, then move one position up or down.
position = ("{% set levels = " + str(LEVELS) + " %}"
            "{% set cur = states('" + MASTER + "') | float(50) %}"
            "{% set ns = namespace(i=0, best=1000) %}"
            "{% for l in levels %}{% if (l - cur) | abs < ns.best %}{% set ns.best = (l - cur) | abs %}{% set ns.i = loop.index0 %}{% endif %}{% endfor %}"
            "{{ [0, [levels | length - 1, ns.i + (1 if trigger.id == 'up' else -1)] | min] | max }}")
level = "{{ " + str(LEVELS) + "[position | int] }}"
config = {
    "alias": "Smart Display - Volume buttons",
    "description": "Physical volume buttons on the den display set one system-wide volume: music, spoken replies and alarms",
    "triggers": [
        {"trigger": "webhook", "id": "up", "webhook_id": "den_display_volume_up",
         "allowed_methods": ["POST"], "local_only": True},
        {"trigger": "webhook", "id": "down", "webhook_id": "den_display_volume_down",
         "allowed_methods": ["POST"], "local_only": True},
    ],
    "actions": [
        {"variables": {"position": position}},
        {"variables": {"level": level}},
        {"action": "number.set_value", "target": {"entity_id": MASTER}, "data": {"value": "{{ level }}"}},
        {"action": "number.set_value", "target": {"entity_id": VOICE},
         "data": {"value": "{{ [1, (position | int * 0.7) | round(0) | int] | max }}"}},
        {"action": "number.set_value", "target": {"entity_id": ALARM},
         "data": {"value": "{{ [" + str(ALARM_FLOOR) + ", level] | max }}"}},
        {"if": [{"condition": "template",
                 "value_template": "{{ state_attr('" + PLAYER + "', 'volume_level') | float(1) < 0.99 }}"}],
         "then": [{"action": "media_player.volume_set", "target": {"entity_id": PLAYER},
                   "data": {"volume_level": 1.0}}]},
    ],
    "mode": "queued", "max": 10,
}
print(subprocess.run([sys.executable, "ha/ha_rest.py", "POST",
                      "/api/config/automation/config/smart_display_volume_buttons", json.dumps(config)],
                     capture_output=True, text=True).stdout)
