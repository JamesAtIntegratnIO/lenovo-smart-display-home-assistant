#!/system/bin/sh
# proxsense: tell Home Assistant when someone is right at the display, from its own infrared
# proximity sensor. /system/bin/proxsense (device/src/proxsense.c) watches the sensor and
# prints a line when the reading rises DELTA above its resting level; this posts each one.
# Home Assistant treats it like a touch (ha/screen_saver.py): it wakes the screen saver.
HA=http://10.0.1.174:8123/api/webhook/kitchen_display_near
DELTA=60   # counts above rest. Measured: rest 38, a person at 3 ft 56, at arm's length 195, a hand at 6 in 1100+

/system/bin/proxsense $DELTA | while read word counts rest; do
  curl -s -m 5 -o /dev/null -X POST -H 'Content-Type: application/json' -d "{\"counts\": $counts, \"rest\": $rest}" "$HA"
done
