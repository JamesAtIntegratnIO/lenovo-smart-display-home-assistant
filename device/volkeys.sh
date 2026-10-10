#!/system/bin/sh
# volkeys: the display's physical volume buttons are bare GPIO lines that only Google's
# (now disabled) assistant app used to read. Watch them and tell Home Assistant about
# each press; Home Assistant owns the actual volume (see ha/volume_buttons.py).
UP=429     # volume up, reads 1 while held
DOWN=576   # volume down, reads 1 while held
HA=http://10.0.1.174:8123/api/webhook

for g in $UP $DOWN; do
  # Normally exported by the Android Things hardware service; export ourselves if not.
  n=0
  while [ ! -e /sys/class/gpio/gpio$g/value ] && [ $n -lt 30 ]; do n=$((n+1)); sleep 2; done
  if [ ! -e /sys/class/gpio/gpio$g/value ]; then
    echo $g > /sys/class/gpio/export
    echo in > /sys/class/gpio/gpio$g/direction
  fi
done

send() { curl -s -m 3 -o /dev/null -X POST "$HA/$1" & }

while true; do
  read u < /sys/class/gpio/gpio$UP/value
  read d < /sys/class/gpio/gpio$DOWN/value
  if [ "$u" = 1 ]; then send den_display_volume_up; sleep 0.25      # repeats while held
  elif [ "$d" = 1 ]; then send den_display_volume_down; sleep 0.25
  else sleep 0.06
  fi
done
