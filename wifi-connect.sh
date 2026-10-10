#!/usr/bin/env bash
# Join Wi-Fi on the display over adb (Android Things has no on-screen keyboard).
# Run inside `nix develop`. Prompts for the SSID and password; nothing is saved.
set -euo pipefail

# With USB and wireless adb both connected, adb needs to be told which one to use
if [[ -z "${ANDROID_SERIAL:-}" ]]; then
  ANDROID_SERIAL=$(adb devices | awk 'NR>1 && $2=="device" {print $1; exit}')
  [[ -n "$ANDROID_SERIAL" ]] || { echo "No adb device found." >&2; exit 1; }
  export ANDROID_SERIAL
fi

read -r -p "Wi-Fi network name (SSID): " ssid
read -r -s -p "Wi-Fi password: " pass
echo

# Single-quote for the device-side shell
q() { printf "'%s'" "${1//\'/\'\\\'\'}"; }

adb shell "am startservice -n com.google.wifisetup/.WifiSetupService \
  -a WifiSetupService.Connect -e ssid $(q "$ssid") -e passphrase $(q "$pass")" >/dev/null

echo "Sent. Waiting for an address..."
for _ in $(seq 1 20); do
  ip=$(adb shell ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}')
  if [[ -n "$ip" ]]; then echo "Connected: $ip"; exit 0; fi
  sleep 2
done
echo "No address after 40s. Check the name and password and run this again." >&2
exit 1
