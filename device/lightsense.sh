#!/system/bin/sh
# lightsense: tell Home Assistant how bright the room is, from the display's own ambient
# light sensor. The sensor is an Android Things "dynamic" sensor that the companion app
# cannot see, but Android's auto-brightness reads it, and `dumpsys display` shows the
# smoothed value it works from (mAmbientLux). That only updates while auto-brightness is on.
# Home Assistant decides what "dark" means (ha/screen_saver.py); this only reports.
HA=http://10.0.1.174:8123/api/webhook/kitchen_display_lux
EVERY=15        # seconds between readings
HEARTBEAT=300   # send at least this often, so Home Assistant can tell the reporter is alive

last=-1; since=$HEARTBEAT
while true; do
  lux=$(dumpsys display | grep -m1 'mAmbientLux=' | cut -d= -f2 | cut -d. -f1)
  case "$lux" in ''|*[!0-9]*) sleep $EVERY; continue ;; esac
  # Send on a change of more than a quarter (or of 2 lux when it is nearly dark), and on the heartbeat.
  diff=$((lux - last)); [ $diff -lt 0 ] && diff=$((-diff))
  step=$((last / 4)); [ $step -lt 2 ] && step=2
  if [ $last -lt 0 ] || [ $diff -ge $step ] || [ $since -ge $HEARTBEAT ]; then
    curl -s -m 5 -o /dev/null -X POST -H 'Content-Type: application/json' -d "{\"lux\": $lux}" "$HA" && { last=$lux; since=0; }
  fi
  sleep $EVERY; since=$((since + EVERY))
done
