#!/usr/bin/env bash
# Turn on Fully Kiosk's Remote Admin (needed by Home Assistant's Fully Kiosk
# integration) and set its password. Run inside `nix develop`.
# Prompts for the password; nothing is saved on the Mac.
set -euo pipefail

# With USB and wireless adb both connected, adb needs to be told which one to use
if [[ -z "${ANDROID_SERIAL:-}" ]]; then
  ANDROID_SERIAL=$(adb devices | awk 'NR>1 && $2=="device" {print $1; exit}')
  [[ -n "$ANDROID_SERIAL" ]] || { echo "No adb device found." >&2; exit 1; }
  export ANDROID_SERIAL
fi

PKG=de.ozerov.fully
PREFS=/data/data/$PKG/shared_prefs/${PKG}_preferences.xml

read -r -s -p "New Fully Remote Admin password: " pass; echo
read -r -s -p "Again: " pass2; echo
[[ "$pass" == "$pass2" && -n "$pass" ]] || { echo "Passwords empty or different." >&2; exit 1; }

# XML-escape, then escape for sed's replacement side
esc=$(printf '%s' "$pass" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g')
sedesc=$(printf '%s' "$esc" | sed -e 's/[\\&#]/\\&/g')

adb root >/dev/null; sleep 2; adb wait-for-device
adb shell am force-stop $PKG
tmp=$(mktemp)
trap 'rm -f "$tmp" "$tmp.new"' EXIT
adb shell cat "$PREFS" > "$tmp"
sed -e 's#<boolean name="remoteAdmin" value="false" />#<boolean name="remoteAdmin" value="true" />#' \
    -e "s#<string name=\"remoteAdminPassword\">[^<]*</string>#<string name=\"remoteAdminPassword\">$sedesc</string>#" \
    "$tmp" > "$tmp.new"
adb push "$tmp.new" /data/local/tmp/fp.xml >/dev/null
adb shell "cat /data/local/tmp/fp.xml > $PREFS; rm /data/local/tmp/fp.xml"
# A force-stopped app does not start on boot, so launch it again now
adb shell monkey -p $PKG -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
sleep 8
ip=$(adb shell ip -4 -o addr show wlan0 | sed -E 's/.*inet ([0-9.]+).*/\1/')
echo "Remote Admin is on: http://$ip:2323/"
