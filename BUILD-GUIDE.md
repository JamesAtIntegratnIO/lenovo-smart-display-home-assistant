# Build guide: Lenovo Smart Display 7 as a Home Assistant voice display

This is a complete record of how a Lenovo Smart Display 7 was taken from stock Google
firmware to a Home Assistant dashboard and voice satellite on 2026-10-09, written so that
someone else can repeat it. It lists every command that was run, in order, with the
reasons, the dead ends, and the sources.

Read this first:

- **This can brick the device.** Step 4 rewrites the preloader, partition table and
  bootloader. Two people in the source thread reported bricks.
- **It wipes the device** and permanently removes the Google Assistant experience. With
  verified boot off, the stock Google UI never finishes starting. Google's update servers
  for this product are gone, so going back to stock may not fully work either.
- **It leaves the device insecure by design**: unlocked bootloader, root shell over
  unauthenticated network adb. Put it on an isolated network and firewall it (step 13).
- Values specific to this build are marked like `192.168.9.253`. A table of them is in
  [Appendix A](#appendix-a-values-specific-to-this-build). Replace them with yours.

Conventions: commands are run from the project folder on a Mac unless a step says
"on the display" (then they run inside `adb shell`). `$AVB_PYTHON` is set by the Nix
shell (step 1). Where a script in this folder does the work, the guide names the script
and says what it does rather than repeating it.

---

## Contents

0. [What you end up with](#0-what-you-end-up-with)
1. [Tools on the computer](#1-tools-on-the-computer)
2. [Connect and enter fastboot](#2-connect-and-enter-fastboot)
3. [Unlock the bootloader and verified boot](#3-unlock-the-bootloader-and-verified-boot)
4. [Flash the firmware](#4-flash-the-firmware)
5. [Root, Wi-Fi and first look](#5-root-wi-fi-and-first-look)
6. [Replace the WebView](#6-replace-the-webview)
7. [Keyboard, and stopping Google's apps](#7-keyboard-and-stopping-googles-apps)
8. [Wireless adb, hosts entry](#8-wireless-adb-hosts-entry)
9. [Home Assistant helpers](#9-home-assistant-helpers)
10. [View Assist Companion: the main screen and voice](#10-view-assist-companion-the-main-screen-and-voice)
11. [The dashboard](#11-the-dashboard)
12. [Voice features](#12-voice-features)
13. [Network: reservation and firewall](#13-network-reservation-and-firewall)
14. [Music: Music Assistant and Spotify](#14-music-music-assistant-and-spotify)
15. [AI conversation agent](#15-ai-conversation-agent)
16. [Physical volume buttons](#16-physical-volume-buttons)
17. [Screen brightness](#17-screen-brightness)
- 17a. [Screen saver: presence, slideshow, dark clock](#17a-screen-saver-presence-slideshow-dark-clock)
18. [Problems hit and how each was diagnosed](#18-problems-hit-and-how-each-was-diagnosed)
19. [Verification checklist](#19-verification-checklist)
20. [Going back](#20-going-back)
- [Appendix A: values specific to this build](#appendix-a-values-specific-to-this-build)
- [Appendix B: versions and file hashes](#appendix-b-versions-and-file-hashes)
- [Appendix C: sources](#appendix-c-sources)
- [Appendix D: what was tried and abandoned](#appendix-d-what-was-tried-and-abandoned)

---

## 0. What you end up with

- The display boots into **View Assist Companion App (VACA)** showing a purpose-built
  Home Assistant dashboard at `/smart-display`, 1024x600 landscape, dark.
- **Voice**: wake word "Okay Nabu" detected on the device, speech-to-text and
  text-to-speech through Home Assistant Cloud, fixed phrases handled locally, and an AI
  agent (Claude) for everything else.
- **By voice**: timers and alarms with an on-screen countdown, cameras by name, NFL
  scores, navigation between screens, Spotify playback through Music Assistant.
- **Hardware buttons**: the volume rocker sets one system-wide volume.

Hardware facts worth knowing up front: MediaTek MT8167S, 32-bit ARM userspace
(`armeabi-v7a`), 2 GB RAM, 1024x600 panel whose natural orientation is portrait,
Android Things 8.1 (API 27), hardware H.264 decode up to 1920x1088.

Prerequisites assumed to exist already:

- Home Assistant (this build: 2026.10.1, Home Assistant OS; see the 2026.10.0 note in step 11) with **HACS** installed.
- **Home Assistant Cloud** subscription, or another Assist pipeline with speech-to-text
  and text-to-speech.
- A long-lived Home Assistant access token saved to `~/.hass_token` (file mode 600).
- A UniFi gateway with zone-based firewall (only for step 13; any firewall will do).
- A USB-A or USB-C to USB-C data cable.
- Optional: Spotify Premium (step 14), an Anthropic API key (step 15).

---

## 1. Tools on the computer

Nix with flakes is used so the tool versions are pinned. `flake.nix` in this folder
provides `adb` and `fastboot` (android-tools 37.0.0) and a Python with `pycryptodome`
(for the AVB unlock), `websockets` and `pyyaml` (for the Home Assistant helpers).

```bash
cd ~/Projects/lenovo-smart-display
nix develop --command sh -c 'adb version | head -2; fastboot --version | head -1'
```

Expected: `Android Debug Bridge version 1.0.41`, `Version 37.0.0-android-tools`,
`fastboot version 37.0.0-android-tools`.

**Gotcha.** `android-tools` puts its own `python3` first on `PATH`, and that one has no
extra libraries. The flake therefore exports the right interpreter as `$AVB_PYTHON`.
Always call `$AVB_PYTHON`, not `python3`, for anything that needs `Crypto`, `websockets`
or `yaml`. (Plain `python3` is fine for `ha/ha_rest.py`, which is stdlib only.)

Without Nix: install Android platform-tools and `pip install pycryptodome websockets pyyaml`,
then set `AVB_PYTHON=python3`.

---

## 2. Connect and enter fastboot

1. Unplug the display's power.
2. Peel back the silicone cover around the power socket. The USB-C port is underneath.
3. Connect USB-C to the computer. A direct port is preferable to a hub.

Booted normally, the stock firmware shows up on USB but offers neither adb nor fastboot:

```bash
ioreg -p IOUSB -l -w 0 | grep -E '"USB Product Name"|"USB Vendor Name"|idVendor|idProduct|"USB Serial Number"'
```

It appears as vendor "Google", product `iot_mt8167s_xl`, ID `0e8d:2008`, with a single
vendor interface (class 255/255/0). `adb devices` and `fastboot devices` are both empty.
That is expected. Fastboot is the only way in.

**Enter fastboot:** with power unplugged, press and hold **Volume +**, plug power in
while still holding, and keep holding for a full **15 seconds**. The screen stays black
in fastboot, so it looks dead. (Releasing after 5 seconds, a tip from someone with the
10-inch model, was too short on this unit and it booted normally.)

A loop that waits for it:

```bash
nix develop --command sh -c 'until [ -n "$(fastboot devices)" ]; do sleep 2; done; fastboot devices -l'
```

Read the state. Nothing here changes the device:

```bash
nix develop --command sh -c 'fastboot getvar all 2>&1 | grep -vE "partition-(size|type)|has-slot"'
nix develop --command fastboot getvar at-vboot-state
```

On this unit: `product: mt8167s`, `unlocked: no`, `secure: yes`, `avb-locked: 1`,
`avb-unlock-disabled: 0` (the unlock is permitted), `current-slot: b`, both slots
`successful`, `max-download-size: 0x6000000`.

**Gotcha.** This bootloader returns garbled replies when fastboot commands arrive back
to back. Leave about a second between commands. The flash script in step 4 does.

---

## 3. Unlock the bootloader and verified boot

Download the two files from the XDA thread's first post into `downloads/` and check
their hashes against [Appendix B](#appendix-b-versions-and-file-hashes):

```bash
mkdir -p downloads && cd downloads
B=https://s3.us-east-1.wasabisys.com/filestash-buk/lenovo-solutions
curl -fSL --retry 3 -O "$B/Lenovo-Android-Things-avb-unlock.zip"        # 4 MB
curl -fSL --retry 5 -C - -O "$B/Ivy-full-flash-15.42.1-1.1.05813256-US.zip"   # 759 MB
shasum -a 256 *.zip
mkdir -p avb-unlock fw
unzip -oq Lenovo-Android-Things-avb-unlock.zip -d avb-unlock
unzip -oq Ivy-full-flash-15.42.1-1.1.05813256-US.zip 'A_Debug/*' 'B_User/*' -d fw
unzip -tq Ivy-full-flash-15.42.1-1.1.05813256-US.zip      # integrity test
cd ..
```

The AVB zip contains a Windows `at_auth_unlock.exe` and, usefully, the original AOSP
`at_auth_unlock.py` plus credential bundles in `creds/` for four Lenovo models. The
Python script works on macOS and Linux. Read it before running it; it is short.

**3a. Check the credentials match before wiping anything.** The unlock is a
challenge-response. Fetching the challenge changes nothing, and it carries a hash of the
device's product ID that must equal the "subject" field of the credential certificate:

```bash
mkdir -p work
nix develop --command sh -c '
fastboot oem at-get-vboot-unlock-challenge; sleep 1
fastboot get_staged work/challenge; sleep 1
$AVB_PYTHON - <<PY
import struct, zipfile, binascii
d = open("work/challenge", "rb").read()
v, h, c = struct.unpack("<I32s16s", d)
print("product hash", binascii.hexlify(h).decode())
cert = zipfile.ZipFile("downloads/avb-unlock/creds/ivy-unlock_credentials.zip").read("puk_certificate_v1.bin")
print("ivy credentials match:", cert[1036:1068] == h)
PY'
```

This unit printed `ivy credentials match: True`. If yours prints `False`, stop.

**3b. Unlock the bootloader. This factory-resets the display.**

```bash
nix develop --command sh -c 'fastboot flashing unlock; sleep 2; fastboot getvar unlocked'
```

Expected: `(bootloader) Start unlock flow`, `OKAY`, then `unlocked: yes`. No on-device
confirmation was asked for.

**3c. Unlock AVB (verified boot).** Reversible with `fastboot oem at-lock-vboot`.

```bash
nix develop --command sh -c 'cd work && $AVB_PYTHON ../downloads/avb-unlock/at_auth_unlock.py -v ../downloads/avb-unlock/creds/ivy-unlock_credentials.zip'
nix develop --command fastboot getvar at-vboot-state
```

Expected: `Found matching unlock credentials`, `Device successfully AVB unlocked`, and
`avb-locked: 0`. (The same output still says `bootloader-locked: 1`. That did not matter.)

---

## 4. Flash the firmware

The XDA zip holds two builds: `A_Debug` (factory/debug) and `B_User` (user build with adb
enabled by the thread's author), and Windows `.cmd` scripts. `flash-debug-things.sh` is a
shell port of the author's `ToDebugThings.cmd`. It:

- refuses to run unless `avb-locked: 0`;
- flashes `boot0` (preloader), the partition table, `tee` and `lk` to both slots;
- puts the **user** build in slot **A** and the **debug** build in slot **B**;
- clears the `factory` persistent digest (the `.cmd` used a Windows helper; the script
  stages the same 37-byte blob itself: little-endian length, the name
  `avb.persistent_digest.factory`, and a zero digest length) and flashes `factory`;
- sets slot A active, reboots to the bootloader and formats `userdata`;
- sends one command at a time with a 1 second pause and stops at the first error.

```bash
nix develop --command ./flash-debug-things.sh downloads/fw 2>&1 | tee work/flash.log
```

It takes about three minutes; the two `system` images are about 35 seconds each. Every
step should print `OKAY`, ending with `FLASH COMPLETE`. Do not unplug anything during it.

Then boot and wait for adb:

```bash
nix develop --command sh -c 'fastboot reboot; adb wait-for-device; adb devices -l; adb shell getprop ro.build.fingerprint'
```

adb appeared about 40 seconds after reboot. Fingerprint:
`Things/iot_mt8167s_xl/mt8167s_xl:8.1.0/OIMC.190719.013/5813256:userdebug/dev-keys`.
The screen shows four spinning dots forever. That is the stock launcher failing to
finish with AVB off, and it is expected.

---

## 5. Root, Wi-Fi and first look

**Root and writable `/system`:**

```bash
nix develop --command sh -c '
adb root; sleep 3; adb wait-for-device
adb disable-verity
adb reboot; sleep 5; adb wait-for-device; sleep 5
adb root; sleep 3; adb wait-for-device
adb remount'
```

Expected: `Successfully disabled verity`, then `remount succeeded`. `adb root` has to be
repeated after every reboot. (The thread also runs `adb shell setenforce 0`. It does not
survive a reboot and nothing here depends on it; see step 16 for the one place SELinux
mattered.)

**Wi-Fi.** The firmware has no on-screen keyboard at all (`adb shell ime list -a -s`
prints nothing), so the settings screen cannot be used to type a password. Android Things
has a service for this. `wifi-connect.sh` wraps it and prompts for the SSID and password
in your terminal, so the password is never stored:

```bash
nix develop --command ./wifi-connect.sh
```

Underneath it runs:

```
adb shell am startservice -n com.google.wifisetup/.WifiSetupService -a WifiSetupService.Connect -e ssid <SSID> -e passphrase <PASSWORD>
```

The clock was at 2010 until Wi-Fi came up, then set itself.

Useful first looks:

```bash
adb shell getprop ro.product.cpu.abilist      # armeabi-v7a,armeabi
adb shell wm size                             # Physical size: 600x1024
adb shell dumpsys webviewupdate | head -5     # stock WebView 66.0.3359.158
adb shell pm list packages | sort
adb exec-out screencap -p > work/screen.png   # screenshots, used throughout
adb shell monkey -p com.android.iotlauncher -c android.intent.category.HOME 1   # Android Things settings screen
```

---

## 6. Replace the WebView

The stock WebView is version 66, far too old for the Home Assistant frontend. Chromium
138 is the last line that supports Android 8. LineageOS publishes prebuilt WebViews; the
ARM one at commit `b2639126d0` is 138.0.7204.63. The APK is stored in Git LFS on
LineageOS's own server, so it has to be fetched through the LFS batch API:

```bash
mkdir -p downloads/apks downloads/backup && cd downloads/apks
OID=b7268786318f404bdad53eaaec889619ff30100b935541a9e393e32efed3cf11
URL=$(curl -s -X POST -H 'Accept: application/vnd.git-lfs+json' -H 'Content-Type: application/vnd.git-lfs+json' \
  -d "{\"operation\":\"download\",\"transfers\":[\"basic\"],\"objects\":[{\"oid\":\"$OID\",\"size\":90257078}]}" \
  https://review.lineageos.org/LineageOS/android_external_chromium-webview_prebuilt_arm.git/info/lfs/objects/batch \
  | jq -r '.objects[0].actions.download.href')
curl -fsSL --retry 3 -o lineage-webview-138.0.7204.63-arm.apk "$URL"
shasum -a 256 lineage-webview-138.0.7204.63-arm.apk     # must equal $OID
cd ../..
```

(The OID and size come from the LFS pointer file at
`https://github.com/LineageOS/android_external_chromium-webview_prebuilt_arm/raw/b2639126d0/webview.apk`.)

Back up the stock one, remove it from `/system`, reboot so Android forgets the package,
then install the new one as an ordinary app:

```bash
nix develop --command sh -c '
adb root; sleep 2; adb wait-for-device
adb pull /system/app/webview/webview.apk downloads/backup/stock-webview-66.0.3359.158.apk
adb remount
adb shell "rm -rf /system/app/webview && sync"
adb reboot; sleep 8; adb wait-for-device
until [ "$(adb shell getprop sys.boot_completed | tr -d "\r")" = 1 ]; do sleep 3; done; sleep 5
adb install -r downloads/apks/lineage-webview-138.0.7204.63-arm.apk
adb shell dumpsys webviewupdate | head -8'
```

Expected: `Current WebView package (name, version): (com.android.webview, 138.0.7204.63)`.

**Why not put it in `/system`?** That was tried first. `/system` had 95 MB free after
removing the old APK and the new one is 90 MB, but the push failed with "No space left on
device" (filesystem reserve). Installing to `/data` works because this is a `userdebug`
build, which does not require the WebView to be a system app.

---

## 7. Keyboard, and stopping Google's apps

```bash
cd downloads/apks
curl -fsSL -o simple-keyboard-148.apk https://f-droid.org/repo/rkr.simplekeyboard.inputmethod_148.apk
cd ../..
nix develop --command sh -c '
adb install -r downloads/apks/simple-keyboard-148.apk
adb shell ime enable rkr.simplekeyboard.inputmethod/.latin.LatinIME
adb shell ime set rkr.simplekeyboard.inputmethod/.latin.LatinIME'
```

Disable the Google packages that otherwise take over the screen or try to update:

```bash
nix develop --command sh -c '
for p in com.google.assistant.core com.google.android.things.internal.iotsetupwizard \
         com.google.android.apps.quartz com.google.android.apps.mediashell \
         com.google.android.things.checkin com.google.android.things.customcheckin; do
  adb shell pm disable $p
done
sleep 15
adb shell "sync; pm list packages -d"'
```

**Gotcha: wait before rebooting.** Android writes these states to disk a few seconds
later. Rebooting immediately lost all six on the first attempt. The `sleep 15` and the
check are there for that reason.

The thread mentions two "gallium" packages to disable. They do not exist on this
firmware. Keep `com.google.wifisetup` (used in step 5),
`com.google.android.things.internal.devicemanagement` (provides the fallback home screen)
and `com.google.android.things.sparrow.oem` (exports the button GPIOs used in step 16).

Disabling `mediashell` removes Chromecast. It was not functional anyway: it was not
listening on the cast port, because Google's setup can no longer complete.

---

## 8. Wireless adb, hosts entry

```bash
nix develop --command sh -c '
adb shell setprop persist.adb.tcp.port 5555
adb reboot'
# afterwards, from the computer:
nix develop --command adb connect 192.168.9.253:5555
```

`ro.adb.secure` is empty on this build, so there is **no adb authentication**. Anything
that can reach port 5555 gets a root shell. Firewall it (step 13). USB adb keeps working
alongside. With both connected, every adb command needs `-s HA0000XX` or
`-s 192.168.9.253:5555`; the scripts in this folder pick one automatically.

Android 8.1 cannot resolve `.local` names (tested: `ping homeassistant.local` fails on
the device while it works from the Mac). VACA uses Home Assistant's configured local URL,
so add a hosts entry:

```bash
nix develop --command sh -c '
adb root; sleep 2; adb wait-for-device; adb remount
adb shell "echo \"10.0.1.174 homeassistant.local\" >> /system/etc/hosts; sync; cat /system/etc/hosts"'
```

---

## 9. Home Assistant helpers

Everything below that touches Home Assistant goes through three small scripts in `ha/`.
They read the token from `~/.hass_token` and talk to `HASS_URL`
(default `http://10.0.1.174:8123`; change the default in each file or export `HASS_URL`).

| Script | Use |
|---|---|
| `ha/ha_rest.py METHOD /api/path ['json']` | Any REST call. Stdlib only. |
| `ha/ha_ws.py call '<json>'` | One WebSocket command, prints the result. Needs `$AVB_PYTHON`. |
| `ha/ha_ws.py save-dashboard <url_path> <file.yaml>` | Replace a dashboard's config. |
| `ha/ask.py "text" …` | Run text through the voice pipeline as if spoken at the display. Prints whether it was handled locally or by the AI, and how long it took. |

Patterns used repeatedly:

```bash
# list states / registries
nix develop --command sh -c '$AVB_PYTHON ha/ha_ws.py call "{\"type\":\"get_states\"}"' | jq ...
# install something from HACS (ids come from hacs/repositories/list)
nix develop --command sh -c '$AVB_PYTHON ha/ha_ws.py call "{\"type\":\"hacs/repository/download\",\"repository\":\"<id>\",\"version\":\"<tag>\"}"'
# run a config flow step by step
python3 ha/ha_rest.py POST /api/config/config_entries/flow '{"handler":"<domain>","show_advanced_options":false}'
python3 ha/ha_rest.py POST /api/config/config_entries/flow/<flow_id> '{...answers...}'
# validate config, then restart Home Assistant
python3 ha/ha_rest.py POST /api/config/core/check_config
python3 ha/ha_rest.py POST /api/services/homeassistant/restart '{}'
# create or replace an automation / script
python3 ha/ha_rest.py POST /api/config/automation/config/<id> '{...}'
python3 ha/ha_rest.py POST /api/config/script/config/<id> '{...}'
```

Everything done this way can equally be done in the Home Assistant UI. The UI path is
given in each step.

---

## 10. View Assist Companion: the main screen and voice

Fully Kiosk Browser was used first (see [Appendix D](#appendix-d-what-was-tried-and-abandoned))
and then replaced by VACA, which gives a dashboard browser, wake word, a voice satellite
and a media player in one free app.

**10a. On the display**

```bash
cd downloads/apks
curl -fsSL -O https://github.com/msp1974/ViewAssist_Companion_App/releases/download/v0.13.5/vaca-0.13.5.apk
cd ../..
nix develop --command sh -c '
adb install -r -g downloads/apks/vaca-0.13.5.apk      # -g grants microphone and camera
adb shell monkey -p com.msp1974.vacompanion -c android.intent.category.LAUNCHER 1'
```

The app shows a blue "Waiting for connection" screen with its IP and port (10800), and a
"Launch on boot" switch that is on by default. Its minimum SDK is 26 and it ships
`armeabi-v7a` libraries, so it runs on this hardware.

**10b. In Home Assistant**

1. HACS: install **View Assist Companion App** (`msp1974/ViewAssist_Companion_App`,
   keep the version equal to the app's, here v0.13.5) and **View Assist**
   (`dinki/view_assist_integration`, here 2026.7.0). Restart Home Assistant.
2. Settings > Devices & services > Add integration > **View Assist Companion App**.
   Auto-discovery (mDNS) does not cross VLANs, so enter host `192.168.9.253`, port `10800`.
   The display plays a tune and switches to the Home Assistant login page.
3. **Log in on the display** with the on-screen keyboard.
4. Add integration > **View Assist**. The first run creates a "Master Configuration"
   entry (submit the empty form). Add it again, choose type `vaca`, name it
   (here "Den display") and pick the VACA device. This step only works after step 3.
   Choose the name with care: the sensor's unique id is built from it (`Den display_vasensor`),
   so renaming it later in Main config makes a new `sensor.*` entity and orphans the old one.
   This display moved to the kitchen; see "Renaming the display" in step 15 for how it was
   renamed to "Kitchen display" without that.
5. HACS (frontend): install **button-card**, **layout-card** and **card-mod**. View
   Assist's own screens show "Configuration error" without them. No restart needed.
   Also install **Advanced Camera Card** (`dermotduffy/advanced-camera-card`); the camera
   views in step 11 are built from it.

The device then has about 45 entities, among them `assist_satellite.vaca_ha0000xx`,
`media_player.vaca_ha0000xx_media_player` and a set of `select.`, `switch.` and
`number.` settings.

**10c. Device settings** (Settings > Devices > VACA device, or by service call):

| Entity | Value | Why |
|---|---|---|
| `select.…_assistant` | Home Assistant Cloud | the pipeline with STT and TTS |
| `select.…_wake_word_engine` | **microwakeword** | openwakeword overloads this CPU, see step 18 |
| `select.…_wake_word` | Okay Nabu | set it again after changing engine; the list differs per engine |
| `number.…_wake_word_threshold` | 6 | the default. 5 was used for the first days (6 only just triggered, score 0.64 vs 0.60) but woke on random kitchen speech: 5 of 7 wakes in a day had no words in them |
| `select.…_wake_word_sound` | Home Assistant | without a chime there is no sign it is listening |
| `number.…_mic_gain` | 5 | restart the app after changing this, see step 18 |
| `select.…_screen_orientation` | landscape | the panel is natively portrait |
| `switch.…_dark_mode` | on | this Android has no system dark mode |

By service call, for example:

```bash
python3 ha/ha_rest.py POST /api/services/select/select_option '{"entity_id":"select.vaca_ha0000xx_wake_word_engine","option":"microwakeword"}'
python3 ha/ha_rest.py POST /api/services/select/select_option '{"entity_id":"select.vaca_ha0000xx_wake_word","option":"Okay Nabu"}'
python3 ha/ha_rest.py POST /api/services/number/set_value '{"entity_id":"number.vaca_ha0000xx_mic_gain","value":5}'
```

**10d. View Assist display options** (the "Kitchen display" entry > Configure > Dashboard options):

| Option | Value |
|---|---|
| Home screen | `/smart-display/home` |
| Music view | `/smart-display/music` |
| Screen mode | Hide header and sidebar |

After changing these, reload the entry and press `button.vaca_ha0000xx_refresh`.

**10e. Updating the companion app later.** Update the integration first, then the app, and
keep the two on the same version. Done here on 2026-10-11 for 0.13.4 to 0.13.5:

```bash
python3 ha/ha_rest.py POST /api/services/update/install '{"entity_id":"update.view_assist_companion_app_update"}'
python3 ha/ha_rest.py POST /api/config/core/check_config        # "valid"
python3 ha/ha_rest.py POST /api/services/homeassistant/restart '{}'
# when Home Assistant is back:
(cd downloads/apks && curl -fsSL -O https://github.com/msp1974/ViewAssist_Companion_App/releases/download/v0.13.5/vaca-0.13.5.apk)
nix develop --command sh -c '
adb install -r -g downloads/apks/vaca-0.13.5.apk     # -r keeps the app data, so every setting survives
adb shell monkey -p com.msp1974.vacompanion -c android.intent.category.LAUNCHER 1'   # the install stops the app; start it again
```

The app can also update itself from a prompt on its screen, but that needs the display to
reach GitHub. After the update here, every VACA entity kept its value (compared before and
after), the `WRITE_SETTINGS` permission from step 17 and the camera grant were still in
place, and `sensor.vaca_ha0000xx_app_version` read 0.13.5. To test the microphone path
without anyone in the room, play speech from the display's own speaker: a text-to-speech
"Okay Nabu" on `media_player.vaca_ha0000xx_media_player` triggered the wake word
(`assist_satellite.vaca_ha0000xx` went to `listening`) in two tries out of three, and with
`number.vaca_ha0000xx_ducking_volume` raised for the test (music is ducked to almost
nothing while it listens; set it back to 1 afterwards), pressing `button.vaca_ha0000xx_wake`
while a spoken question played came back from cloud speech-to-text as text and was answered.

---

## 11. The dashboard

A separate dashboard, so the main Overview is untouched. It is generated by
`ha/build_smart_display.py`, which reads a dump of the Overview and copies the
quick-action, roof-theme and back-yard buttons from it by section name so they behave
identically. You will need to edit that file for your own entities.

```bash
mkdir -p work/ha
nix develop --command sh -c '
$AVB_PYTHON ha/ha_ws.py call "{\"type\":\"lovelace/config\",\"url_path\":null}" > work/ha/overview.json
$AVB_PYTHON ha/ha_ws.py call "{\"type\":\"lovelace/dashboards/create\",\"url_path\":\"smart-display\",\"title\":\"Smart Display\",\"icon\":\"mdi:tablet-dashboard\",\"show_in_sidebar\":true,\"require_admin\":false,\"mode\":\"storage\"}"
$AVB_PYTHON ha/build_smart_display.py work/ha/overview.json ha/smart-display.yaml
$AVB_PYTHON ha/ha_ws.py save-dashboard smart-display ha/smart-display.yaml'
```

(The `dashboards/create` call is needed once. After that only the last two lines.)

Design decisions, all learned by looking at screenshots from the device
(`adb exec-out screencap -p`):

- At 1024 px wide, a sections view fits **two** columns, not three.
- The Home Assistant top bar is hidden on the display (step 10d), so every view starts
  with its own row of eight icon buttons for navigation (eight buttons three grid
  columns wide fill the row exactly).
- Views: **Home** (clock, thermostat, timers card, quick actions, door locks),
  **Lights**, **Cameras** (2x2 grid), **Outside**, **Music**, **Media** (TV, vacuum),
  **Sports** (TeamTracker card), **Alarm** (stock `alarm-panel` card for the alarm panel
  with Arm home / Arm away, next to tiles for the door, window and motion sensors and the
  panel fault sensor). The alarm card only draws its keypad when the alarm entity reports
  `code_format: number`; with the Alarm.com custom integration that means setting an arm
  code in the integration's options. The keypad and the four tiles fit the 600 px screen
  without scrolling.
- Cameras use [Advanced Camera Card](https://card.camera). The grid shows a snapshot of
  each camera that refreshes every 10 seconds; tapping one opens that camera live on its
  own full-screen view (`/smart-display/cam-<name>`), and tapping the live picture goes back
  to the grid. Four live pictures at once are too much for this CPU; "Live video" below has
  the numbers.
- The timers card is a Markdown card that renders the `timers` attribute of
  `sensor.den_display`. It updates when a timer changes and once a minute.

**Cameras.** UniFi Protect's "High resolution channel" entities are beyond this display.
Enable the "Medium resolution channel" entity of each camera (disabled by default) and
use those. In the UI: the camera's device page > the disabled entity > Enable. By API:

```bash
nix develop --command sh -c '$AVB_PYTHON ha/ha_ws.py call "{\"type\":\"config/entity_registry/update\",\"entity_id\":\"camera.front_driveway_medium_resolution_channel\",\"disabled_by\":null}"'
```

They appear about 30 seconds later. If they stay unavailable, enable the Medium RTSP
stream for that camera in Protect.

**Live video: Advanced Camera Card over HLS.** `camera()` in `ha/build_smart_display.py`
builds every camera card. What it sets, and why:

- `profiles: [low-performance]` removes the menu, thumbnails, timeline and loading effects.
  That profile also replaces live video with snapshots, so a live card sets
  `live_provider: ha` (Home Assistant's own stream) and a grid tile sets `image`.
- Grid tiles ask Home Assistant for a picture the size of a tile
  (`image.entity_parameters: width=480&height=270`). Without it the card fetches the
  camera's full frame, about 1.3 MB every 10 seconds per camera, and the grid cost half a
  core more than the stock picture cards.
- `live.lazy_unload` and `live.auto_pause` on `unselected` and `hidden`, and no built-in
  video controls. A card only streams while its view is open: leaving the view removes the
  card and the stream with it.
- In a panel view the card leaves 56 px for Home Assistant's header, which is hidden on the
  display. `view.theme.overrides: {"--kiosk-header-height": "0px"}` gives the picture the
  whole screen.

The stream type matters more than the card. Home Assistant offers WebRTC and HLS, and both
the stock cards and Advanced Camera Card pick WebRTC. On this display WebRTC does not stay
live: it runs at 20-25 fps for 20-30 seconds, then drops to 0-3 fps with freezes of ten
seconds and more. WebRTC arrives over UDP, and about one packet in five is lost on the
display's Wi-Fi link (the browser's WebRTC statistics showed 988 lost of 5,343; the kernel's
own UDP error counters stayed at zero, so the loss is before the network stack; `ping` and
TCP are fine). Home Assistant's WebRTC server does not resend, so every lost packet freezes
the picture until the next keyframe. HLS comes over TCP on the same connection as the rest
of the dashboard and is decoded in hardware.

`ha/frontend/hls_only.js` makes the display use HLS. It wraps the frontend's WebSocket
call for `camera/capabilities` and trims the answer to `["hls"]`, only when the user agent
says it is this display (`mt8167s`). Install it with:

```bash
nix develop --command sh -c '$AVB_PYTHON ha/hls_only.py install'    # or: remove | status
```

It is a `data:` URL dashboard resource, like the screen saver card, so nothing is copied to
Home Assistant. It applies to every live camera on the display, including View Assist's own
camera screen and the stock more-info dialog. Reload the display's page after installing
(restart the app, or `location.reload()` through the remote debugger).

What HLS costs: the picture is about 4 seconds behind real time, and a camera that has not
been viewed in the last minute takes 5 to 10 seconds to start (a still picture shows
meanwhile; about 2 seconds when the stream is still warm). Home Assistant's "preload
stream" camera setting cut a cold start from about 9 to about 5 seconds in one test and
keeps an RTSP session open per camera all day; it is off here.

Measured on the display on 2026-10-11 (60-second windows over adb, freshly loaded page,
CPU in cores busy out of 4, read from `/proc/stat`):

| View | Stock cards, WebRTC | Advanced Camera Card, HLS |
|---|---|---|
| Home | 0.95 | 0.92 |
| Cameras grid (4 snapshots) | 0.98 | 1.11 |
| One camera after a tap (doorbell, 20 fps source) | 1.39 cores, 1.5 fps shown | 2.21 cores, 20.3 fps, 0 of 1,221 frames dropped |
| One camera full screen (driveway, 30 fps source) | 1.67 cores, 2.8 fps shown, 21 of 171 dropped | 2.76 cores, 30.7 fps, 0 of 1,846 dropped |
| Four live tiles (tried, not used) | not tried | 3.85 cores, 18 fps, about half the frames dropped |

Live video costs about one core more than before because every frame is now decoded and
drawn; before, the display spent most of a live view showing a frozen frame. The cost is
frame rate, not resolution: the 640x360 "Low resolution channel" measured the same 2.6
cores as the 1280x720 one. During a live view the app process (which hosts the WebView's
GPU thread) uses about 1.45 cores and the renderer 0.5. Memory: the renderer grows by about
70 MB on the camera views (158 to 231 MB PSS on the grid); 1.05 GB stays available.

With a live picture up, the wake word was caught 4 times out of 4 (spoken through the
display's own speaker) and answered in 4.6 to 6.7 seconds, against 3 of 3 in 4.6 to 5.8
seconds on the Home view, and the video held 30 fps throughout.

If the extra core ever matters, set `live=False` on the full-screen views in
`ha/build_smart_display.py`: they then show a still that refreshes (set
`refresh_seconds` to 1 or 2), at about the cost of the grid.

To preview a view on the device and capture it:

```bash
python3 ha/ha_rest.py POST /api/services/view_assist/navigate '{"device":"sensor.den_display","path":"/smart-display/cameras"}'
nix develop --command sh -c 'sleep 7; adb -s HA0000XX exec-out screencap -p > work/view.png'
```

**Camera on detection or doorbell.** `nix develop --command sh -c '$AVB_PYTHON ha/camera_takeover.py'`
creates the automation "Smart Display - Show camera on detection or doorbell" and the one
helper it needs (`input_text.den_display_takeover_return`). Edit `CAMERAS` and
`DOORBELL_RING` at the top of the file for your own entities first.

- **Triggers:** UniFi Protect's person and vehicle detection sensors for each camera going
  on, and the doorbell's ring event. Raw motion is left out on purpose: it fires on
  shadows and trees and would take the screen over all day.
- **What it does:** remembers the display's current view in the helper (read from
  `sensor.vaca_…_current_path`, the companion app's own report of its page; View Assist's
  `current_path` never sees a tab opened by touch), then opens that
  camera's full-screen view, `/smart-display/cam-<name>?takeover=1`, with
  `revert_timeout: 0`, so View Assist leaves the camera up until the automation gives the
  screen back. `VIEWS` in the script maps each camera to its view; the names are the slugs
  in `CAMERAS` in `ha/build_smart_display.py`. A still picture shows at once and the live
  picture takes over 5 to 10 seconds later (HLS start-up, see "Live video" above).
- **Going back:** every 3 seconds it checks that camera's sensors. When they have all been
  off for `CLEAR_SECONDS` (30), or after `MAX_SECONDS` (300) whatever happens, it navigates
  to the remembered view, with `revert_timeout: 0` again (without it View Assist sends any
  view but its home screen home 20 seconds later). View Assist's mode is never changed. (Until 2026-10-11 the
  takeover used View Assist's own camera screen, which sets the mode to "hold"; the
  automation had to restore it and wait a second before navigating.)
- **If a voice request or another automation moves the display during a takeover,** the
  automation notices within 3 seconds and leaves the display where it is. That includes a
  touch (a tap on the live picture opens the camera grid): from 10 seconds into a takeover
  the display's own path is checked as well, and the automation then only tells View Assist
  where the display is, so its `current_path` does not keep the `takeover=1` marker.
- **Several cameras:** a showing takeover is not replaced by another camera. One person out
  front trips the doorbell, driveway and landscape cameras in turn, and with "newest
  detection wins" the screen hopped between them (86 triggers in one day, ten view changes
  in five minutes). Only the doorbell, its camera or a ring, takes the screen from another
  camera; the first return point is kept (the `takeover=1` marker plus a camera view on the
  display is how the automation recognises its own takeover). For `COOLDOWN_SECONDS` (120)
  after a takeover starts, cameras other than the doorbell cannot start a new one. For
  `RING_HOLD_SECONDS` (30) after a doorbell ring, only the doorbell camera may take the screen.
- **Do Not Disturb** on the View Assist device stops takeovers. Disabling the automation
  turns the feature off.

To test without walking outside, write a state straight into Home Assistant. The
integration overwrites it on the camera's next real update:

```bash
S=binary_sensor.g6_bullet_person_detected_2   # your driveway person sensor
python3 ha/ha_rest.py POST /api/states/$S '{"state":"on"}'; sleep 15
python3 ha/ha_rest.py POST /api/states/$S '{"state":"off"}'   # display returns about 30 s later
# a doorbell ring is a new timestamp on the event entity
python3 ha/ha_rest.py POST /api/states/event.g4_doorbell_pro_poe_doorbell \
  "{\"state\":\"$(date -u +%Y-%m-%dT%H:%M:%S.000+00:00)\",\"attributes\":{\"event_types\":[\"ring\"],\"event_type\":\"ring\",\"device_class\":\"doorbell\"}}"
```

**Gotchas.**

- View Assist navigates to its home screen whenever the mode changes. The takeover no
  longer changes the mode, so it returns straight to the previous view. Anything that does
  change it has to restore the mode, wait a second, then navigate.
- A view other than Home is still subject to View Assist's own view timeout afterwards
  (20 seconds here), exactly as if it had been opened by voice.
- **Home Assistant 2026.10.0 only (fixed in 2026.10.1, workarounds retired):** opening a
  camera live flipped its entity to `unavailable`. That release moved to FFmpeg 9, which
  verifies TLS certificates by default, and Protect serves RTSPS with a self-signed
  certificate, so the HLS stream worker failed ("Error opening stream (I/O error,
  rtsps://…)") while the display's WebRTC picture was fine. This is
  [home-assistant/core#184775](https://github.com/home-assistant/core/issues/184775), fixed
  in 2026.10.1 (PRs 184877 and 184930). Skip 2026.10.0 if you can.

  The same bug blanked the camera snapshots on the display. Home Assistant's frontend starts
  an HLS player next to the WebRTC one for every live camera view. On 2026.10.0 the HLS
  playlist request (`/api/hls/<token>/master_playlist.m3u8`) never got an answer and was not
  cancelled when the view closed, so each live view left two requests hanging for good. A
  browser allows six connections per server, so after three live views every later request
  to Home Assistant queued forever: grey tiles or broken-image icons on the Cameras grid,
  and even a page reload hung. Home Assistant itself was fine throughout (the same snapshot
  URL answered `curl` from the display in half a second), which is what made it confusing.

  This build carried two workarounds for those two days: an automation that reloaded the
  UniFi Protect integration after a camera dropped (`ha/protect_stream_workaround.py`), and
  a dashboard resource that refused `/api/hls/` requests on the display only
  (`ha/hls_guard.py`, `ha/frontend/hls_guard.js`). Both were removed on 2026-10-11 after
  updating to 2026.10.1 and are no longer in this folder (they are in the git history up to
  commit `8f00dbf`). The test that retired them, with both switched off: six live views in a
  row across the four cameras. Every camera entity stayed `recording`, the master playlist
  answered `200` each time, nothing was left pending, and the snapshot grid loaded
  afterwards.

  How it was found, since this technique is useful for any display-side problem: the WebView
  exposes Chrome's remote debugger.

  ```bash
  adb shell 'cat /proc/net/unix | grep -o "webview_devtools_remote_[0-9]*"'
  adb forward tcp:9333 localabstract:webview_devtools_remote_<pid>
  curl -s http://127.0.0.1:9333/json        # lists pages with a webSocketDebuggerUrl
  ```

  Speaking the DevTools protocol to that WebSocket (`Network.enable`, then watch
  `requestWillBeSent` / `loadingFinished`) showed which requests never finished, and
  `adb shell netstat -tn | grep 8123` showed the six-plus-one connections pinned open.

---

## 12. Voice features

Home Assistant tries sentence-trigger automations and built-in intents first, and only
then the conversation agent. All of the following are sentence triggers, so they are
instant and cost nothing.

**12a. Timers, alarms, reminders.** Out of the box, "set a timer" uses Home Assistant's
built-in satellite timer, which has no on-screen form. View Assist's blueprint replaces
it with timers the screen can show, and switches to a countdown screen when asked or when
one rings.

Settings > Automations > Blueprints > "View Assist - Alarms Reminders Timers" > Create,
with "Use VACA onboard sound" on. The exact inputs used are in
`ha/blueprint_automations.py`.

Phrases: "set a timer for 5 minutes", "show me my timers", "how much time is left on my
timer", "cancel my timer", "snooze".

**12b. Sports scores.**

1. HACS: **TeamTracker** integration (`vasqued2/ha-teamtracker`) and **TeamTracker Card**
   (`vasqued2/ha-teamtracker-card`). Restart Home Assistant.
2. Add integration > TeamTracker > Football > NFL > search "Seahawks" > name it
   `Seahawks` (gives `sensor.seahawks`, used on the dashboard).
3. Add it a second time with the name `team_tracker` (gives `sensor.team_tracker`).
   View Assist's blueprint repoints this one at whichever team is asked about.
4. Create an automation from the blueprint "View Assist - Get Sports Scores" with
   `team_tracker: sensor.team_tracker` and the extended phrase list in
   `ha/blueprint_automations.py`. The blueprint ships with only four phrasings; the
   additions cover "get/show me/what's the … score", "did the … win", "when do the …
   play" and similar.
5. Create the "Sports default team" automation from the same file. Without it, a request
   with no team in it ("get sports scores") reports whichever team was asked about last.
   It points the shared tracker back at the Seahawks 90 seconds after any other team.

**Gotcha.** Repointing the tracker by REST with `entity_id` in the body did nothing.
It only worked as an automation action with a `target:` block, which is the form in the file.

**12c. Cameras by voice.** `python3 ha/camera_voice.py` creates one automation with a
sentence trigger per camera, each listing that camera's spoken names, plus one for "all
cameras". A single camera opens its full-screen live view (`/smart-display/cam-<name>`,
the same Advanced Camera Card views the takeover uses) for 120 seconds
(`revert_timeout`); "all cameras" opens the dashboard grid.
View Assist's own camera blueprint was not used: it requires the word "camera" in every
request and uses one catch-all slot for the name, which would also capture "show me my
timers".

**12d. Navigation.** `python3 ha/nav_voice.py` creates "go home", "show me the lights",
and similar for each dashboard view. A view opened by voice stays up like one opened by
touch: the navigation is sent with `revert_timeout: 0`, as is "show all cameras" in 12c
(without it View Assist goes home after its 20 second view timeout). A single camera asked
for by name still closes after `SHOW_SECONDS` (120).

**12d-2. Back to the tab after an answer.** `python3 ha/tab_return.py` creates "Smart Display -
Back to the tab after a voice answer". A spoken answer, a timer or an alarm opens one of View
Assist's own views (`/view-assist/info`, `/view-assist/alarm`), and when it closes View Assist
goes to its home screen whatever tab was showing. The automation notes the tab the answer
opened over (from `sensor.vaca_…_current_path`) and navigates back to it when the display
lands on Home. Not used from Home, the saver or a camera takeover, which look after themselves.

**12e. Music phrases.** Blueprint "View Assist - Play Music with Music Assistant", after
step 14. Inputs in `ha/blueprint_automations.py` (`view_path: /smart-display/music`, and
`play_artist_command` with the default's "play some {artist}" removed). The default treats
every "play some X" as an artist, so "play some oldies" played a stock-music artist called
"Oldies Playing". Without it, "play some X" goes to the AI (step 15), which decides between
artist and genre; "play music by X" and "start the X playlist" are still answered locally.

Test any of it without speaking:

```bash
nix develop --command sh -c '$AVB_PYTHON ha/ask.py "show me the front driveway" "how are the seahawks doing"'
```

---

## 13. Network: reservation and firewall

Done here on a UniFi gateway with zone-based firewall (zones "Internal" and "IOT").

1. **DHCP reservation** for the display's Wi-Fi MAC so its address never changes
   (Client > Settings > Fixed IP). Read the MAC with
   `adb shell cat /sys/class/net/wlan0/address`.
2. **Restrict adb.** Two policies, Internal > IOT, TCP, destination
   `192.168.9.253` port `5555`, placed above any broad "allow Internal to IOT" rule:
   - ALLOW, source = the admin computer (matched by its wired MAC);
   - REJECT, source = any.
   Verified by connecting from the wired address (works) and with
   `nc -z -w 4 -s <wifi address> 192.168.9.253 5555` (refused).
   The gateway cannot filter traffic between devices inside the IoT VLAN.
3. **Let the display reach Home Assistant.** The IoT network needs TCP to the Home
   Assistant host on **8123** (frontend and API) and **8097** (Music Assistant's stream
   server). Here an existing rule allowed `1883,8123`; it became `1883,8123,8097`.
   Without 8097, music shows as "playing" and is silent (step 18).

Traffic from Home Assistant to the display needs TCP 10800 (VACA) allowed; here a broad
Internal-to-IOT allow already covered it.

---

## 14. Music: Music Assistant and Spotify

1. Settings > Add-ons > Add-on store > **Music Assistant** > Install > Start, with
   "Show in sidebar" on. (Version here: 2.10.6.)
2. Home Assistant discovers it; confirm the **Music Assistant** integration.
3. Open Music Assistant from the sidebar and finish its first-run screens.
4. Music Assistant > Settings > **Player providers** > Add > **Home Assistant
   MediaPlayers**, and tick the display's player ("VACA ha0000xx Media Player"). A new
   entity `media_player.vaca_ha0000xx_media_player_2` appears in Home Assistant. That is
   the one to play music to.
5. Music Assistant > Settings > **Music providers** (music sources) > Add > **Spotify**,
   and sign in. Requires Premium.
   **Not** "Spotify Connect" under plugins, and not Home Assistant's own Spotify
   integration: neither can search the catalogue, so voice requests find nothing.
6. In View Assist's "Kitchen display" entry > Configure > Main config, set **Music player
   device** to `media_player.vaca_ha0000xx_media_player_2`.
7. Open the firewall port from step 13.3.
8. Create the music blueprint automation (step 12e).

Test the path with a radio stream before involving Spotify, and check the device, not
just Home Assistant's state:

```bash
python3 ha/ha_rest.py POST /api/services/music_assistant/play_media '{"entity_id":"media_player.vaca_ha0000xx_media_player_2","media_id":"https://ice1.somafm.com/groovesalad-128-mp3","media_type":"radio"}'
nix develop --command sh -c 'adb -s HA0000XX shell "logcat -d | grep -E \"MusicPlayerService|AudioTrack|musicPlayerPlayingStatus\" | tail -5"'
```

A healthy run logs `Playing music: http://<ha>:8097/single/…`, an `AudioTrack` line and
`musicPlayerPlayingStatus - true`.

---

## 15. AI conversation agent

1. Create an API key at <https://console.anthropic.com>.
2. Settings > Devices & services > Add integration > **Anthropic**, paste the key.
3. `python3 ha/music_tool.py` then does three things (each also possible in the UI):
   - creates `script.den_display_play_music`, a script with fields `query`,
     `media_type`, `artist` and `radio_mode` that plays on the display's player through
     Music Assistant, switches the display to the Music view and returns what it
     started. Scripts exposed to voice become tools the AI can call, and the script's
     description is what it reads;
   - creates "Smart Display - Shuffle local music requests", which turns shuffle on when
     the music blueprint (step 12e) fires;
   - reconfigures the Claude conversation agent: the prompt in the file, model
     `claude-haiku-5-5`, max tokens 1024, web search on with at most 2 uses, user
     location on;
   - `python3 ha/phone_link_tool.py` creates `script.send_link_to_phone` ("Send a link to
     the owner's phone", fields `url`, `title`, `summary`) and exposes it to voice. It calls
     `notify.mobile_app_your_phone` with the page as the notification's tap action
     and an "Open" button, refuses anything that is not an http(s) address, and returns
     whether it sent. Change `NOTIFY` in the file for a different phone;
   - (the two ids `ENTRY` and `SUB` near the bottom are this install's config entry and
     subentry ids; get yours from `config_entries/get` and `config_entries/subentries/list`).
4. Expose the script and the player to voice (Settings > Voice assistants > Expose), or:
   ```bash
   nix develop --command sh -c '$AVB_PYTHON ha/ha_ws.py call "{\"type\":\"homeassistant/expose_entity\",\"assistants\":[\"conversation\"],\"entity_ids\":[\"script.den_display_play_music\",\"media_player.vaca_ha0000xx_media_player_2\"],\"should_expose\":true}"'
   ```
5. Settings > Voice assistants > the pipeline > Conversation agent: **Claude
   conversation**, and turn on **Prefer handling commands locally**. By API:
   `assist_pipeline/pipeline/update` with `conversation_engine: conversation.claude_conversation`
   and `prefer_local_intents: true` (all other fields must be resent unchanged).

Door locks are not exposed to voice by default. If you expose them, remember that
"unlock the front door" then works for anyone in earshot.

**How genres are played.** A genre, era or mood ("oldies", "80s", "dinner music") is not
something Spotify can play, and a free search for one returns whatever is named after it.
For `media_type: genre` the script searches playlists only and ranks them: Spotify's own
editorial playlists first (ids starting `37i9dQZF1D`), then its genre mixes (`37i9dQZF1E`,
except the per-song "... Radio" ones, `37i9dQZF1E8`), then everyone else's; within a tier a
name containing every word asked for wins. "Oldies" lands on "Classic Oldies", "classic
rock" on "Rock Classics", "80s" on "All Out 80s". The prompt tells the AI to use `genre`
for these rather than guess an artist or playlist itself.

**Shuffle.** Genre, artist and playlist plays are shuffled so they do not open on the same
song every time; an album or a single track plays in order. The blueprint's local phrases
never set shuffle and the queue keeps whatever the last request left, hence the small
automation that turns it on whenever the blueprint fires.

**Recipes and other lookups.** Asked "how do I make peach cobbler", the agent used to recite a
generic recipe from memory. The prompt now makes it web search for recipes, how-tos and
product picks, answer from one specific well-known page, name the site and the recipe with a
one-sentence summary, and call "Send a link to the owner's phone" with that page's exact address.
Two details matter. Home Assistant speaks only the text that follows the last tool call, so
the prompt tells the agent to send the link first and put the whole answer after it; in the
first attempt it named the source before the call and all that was spoken was "The link is on
the owner's phone." And the address must come from the search results, never be composed, which
the script's field description repeats. Haiku 5.5 does this in 5 to 8 seconds and picked real
pages (Add a Pinch, Food Network, The Kitchn, Bissell) in testing, so a larger model was not
needed. Every such request sends a notification; there is one phone registered, so links go
to that phone whoever is asking.

**Renaming the display.** The display moved from the den to the kitchen on 2026-10-10. Only
names were changed, by entity registry name override or alias, so every entity id, webhook id
and automation reference is as before: the View Assist entry title and `sensor.den_display`'s
name, the Music Assistant player's name (the one the AI is told to use), the play-music
script's alias, the takeover helper's name, and the old Google cast device. The three devices
were also put in the Kitchen area. View Assist's own `name` attribute still reads "Den
display" because changing it changes the sensor's unique id. `input_text/update` resets any
field it is not given, so resend `max: 255` and the icon when renaming that helper.

**Why the prompt says what it says.** A request answered by a sentence-trigger automation
appears in the AI's conversation history as an assistant reply with no tool call behind
it. Before the prompt explained that, the AI told the user that "Playing rock music" had
"not been a real action" and retracted it, although music was playing. The prompt now
lists what is handled before the AI sees it and forbids retracting those.

---

## 16. Physical volume buttons

**Finding.** The rocker does nothing after step 7. The buttons are not Android keys:
`getevent -pl` lists only a volume-down key on `mtk-pmic-keys` and no volume-up, and
pressing either produces no input event. They are bare GPIO lines that Google's (now
disabled) app used to read. They were found by watching the exported GPIOs while pressing:

```
adb root
adb shell 'for g in 397 406 429 492 494 496 576; do echo "gpio$g $(cat /sys/class/gpio/gpio$g/direction) $(cat /sys/class/gpio/gpio$g/value)"; done'
```

then polling the four inputs in a loop and pressing up three times, then down three
times. **GPIO 429 = volume up, GPIO 576 = volume down**, both read 1 while held.

**Design.** A watcher on the display posts a webhook to Home Assistant on each press, and
a Home Assistant automation changes the volume. It goes through Home Assistant because
changing volume locally is too slow on this hardware (`media volume --set` and
`input keyevent` each take over a second) and the fast `service call audio …` route had
no effect.

**16a. Home Assistant side:** `python3 ha/volume_buttons.py` creates an automation with
two local-only webhooks (`den_display_volume_up`, `den_display_volume_down`).

The display has three separate volume controls, and the automation drives all of them
from one position so the rocker is system-wide:

| Control | Entity | Scale |
|---|---|---|
| Android media stream (music and most sound) | `number.…_music_volume` | 0 to 100 |
| Spoken replies and chime | `number.…_voice_volume` | 0 to 7 |
| Timers and alarms | `number.…_alarm_volume` | 0 to 100, floored at 60 |
| Music Assistant player gain | `media_player.…_media_player_2` | pinned at 100% |

The media stream's volume curve is steep and mostly inaudible in its lower half. Read it with:

```
adb shell dumpsys media.audio_policy | grep -A3 "AUDIO_STREAM_MUSIC"
```

On this device: index 10 = -46 dB, 30 = -33.5 dB, 50 = -21 dB, 60 = -15 dB,
80 = -7.5 dB, 100 = 0 dB. Even steps of 10 therefore feel like nothing at the bottom and
big jumps at the top. The automation uses ten positions 3 dB apart instead:
`0, 40, 45, 50, 55, 60, 68, 76, 84, 92, 100`. It finds the position nearest the current
value and moves one up or down.

**16b. Display side:** `device/volkeys.sh` polls the two GPIO files and runs
`curl -X POST http://10.0.1.174:8123/api/webhook/den_display_volume_up` (or `_down`),
repeating every 0.25 s while held. `device/volkeys.rc` starts it at boot.

```bash
nix develop --command sh -c '
adb -s HA0000XX root; sleep 2; adb -s HA0000XX wait-for-device
adb -s HA0000XX remount
adb -s HA0000XX push device/volkeys.sh /system/bin/volkeys.sh
adb -s HA0000XX push device/volkeys.rc /system/etc/init/volkeys.rc
adb -s HA0000XX shell "chmod 755 /system/bin/volkeys.sh; chmod 644 /system/etc/init/volkeys.rc; sync"
adb -s HA0000XX reboot'
# after boot:
nix develop --command adb -s HA0000XX shell 'getprop init.svc.volkeys; ps -A -o PID,USER,LABEL,ARGS | grep volkeys'
```

Expected: `running`, and the process in the `u:r:su:s0` context.

**Gotcha: SELinux.** The first init entry used `seclabel u:r:su:s0` and the service sat in
`restarting`. `dmesg` showed
`avc: denied { transition } … scontext=u:r:init:s0 tcontext=u:r:su:s0`. The `shell`
domain can be entered from init but cannot read the GPIO files. What works is
init > `shell` domain > `/system/xbin/su`, the same path `adb shell su` takes:

```
service volkeys /system/bin/sh -c "exec /system/xbin/su 0,0,3003 /system/bin/sh /system/bin/volkeys.sh"
    seclabel u:r:shell:s0
```

`0,0,3003` is uid root, gid root, plus the `inet` group for network access.

---

## 17. Screen brightness

VACA's auto-brightness uses Android's adaptive brightness. The built-in curve gives about
39% in a normal room (100 lux) and jumps from 47% to 100% between 150 and 300 lux. Read it with:

```
adb shell dumpsys display | grep -E "mScreenAutoBrightnessSpline|mAmbientLux|mScreenAutoBrightness="
```

Android's own bias setting lifts the low end and flattens the curve
(brightness becomes `x ^ (3 ^ -adj)`):

```
adb shell settings put system screen_auto_brightness_adj 0.7
```

Measured at 105 lux: 100/255 before, 165/255 after. It does not change how quickly the
display reacts (2 s to brighten, 4 s to dim, fixed in the firmware).

---

## 17a. Screen saver: presence, slideshow, dark clock

The dashboard is static, so the panel needs protecting. Added 2026-10-10. The screen is
never turned off; it shows something that moves instead.

| When | What the display shows |
|---|---|
| nobody there for `SAVER_MINUTES` (5), room bright | full-screen photo slideshow with a clock over it |
| nobody there for 5 minutes, room dark | a dim clock on black that drifts to a new spot every minute |
| touch, wake word, volume rocker, someone within about two feet | the view it was on before |
| someone moving elsewhere in the room | no change: the saver stays, and so does the dashboard |
| camera takeover, ringing timer, a voice request that opens a view | that view wins; the saver stands down |

Settings are constants at the top of `ha/screen_saver.py`: `SAVER_MINUTES` 5, `DARK_LUX` 3,
`BRIGHT_LUX` 8, `LUX_STALE_MINUTES` 15, `SUN_DARK_DEGREES` -4, `MOTION_MODE` "motion",
`MOTION_SENSITIVITY` 20. How close "within about two feet" is, is `DELTA` in
`device/proxsense.sh` (step 17a.3a).

Two sensors answer two different questions. The camera says whether anyone is around, and
only decides when the saver may start. The proximity sensor says whether someone is at the
display, and with touch and voice is the only thing that ends a saver.

**What View Assist and VACA already offer, and why it was not enough.** View Assist can
rotate the *background* of its own views (clock, weather) from a folder or an entity; it
does not cover a custom dashboard and has no idle logic. VACA has a "Screen saver" switch
(a black overlay that a tap clears), a "Screen" switch and a "Screen timeout". On this
device the last two do not turn the panel off (VACA logs "Simulating screen off via timeout
and black overlay", and a tap does not clear that one). So the saver is a small custom
card, and Home Assistant decides when to show it.

**17a.1 Presence: make the camera usable.** VACA has camera detection built in
(`select.…_motion_detection` none/motion/face, `binary_sensor.…_motion`,
`number.…_motion_detection_sensitivity`), which is the lightest route since no extra process
runs. On this firmware it fails at start:

```
CameraValidator: Camera LENS_FACING_FRONT verification failed
CameraX: No available camera can be found. Cams:0 … LensFilter:0
```

`adb shell dumpsys media.camera` shows why: one camera, HAL v1.0, `Facing: Back`, while the
feature list claims both a back and a front camera. VACA asks CameraX for a front camera.
Two changes fix it. Keep copies of both files first (`downloads/backup/`).

1. The facing comes from the camera's static metadata, built by
   `constructCustStaticMetadata_DEVICE_CAMERA_COMMON` in `/vendor/lib/libcam.metadataprovider.so`.
   For camera 0 it stores facing 1 (back; 0 is front). In the build with SHA-256
   `6ba9ca58…d612ac83` that is the Thumb instruction `movs r0, #1` (bytes `01 20`) at file
   offset `0x4dc6`. Change the first byte to `00`:

   ```bash
   adb pull /vendor/lib/libcam.metadataprovider.so work/camhal/
   python3 - <<'PY'
   import pathlib
   b = bytearray(pathlib.Path("work/camhal/libcam.metadataprovider.so").read_bytes())
   assert b[0x4dc6:0x4dc8] == bytes.fromhex("0120")     # stop if this is a different build
   b[0x4dc6] = 0
   pathlib.Path("work/camhal/libcam.metadataprovider.front.so").write_bytes(b)
   PY
   adb remount
   adb push work/camhal/libcam.metadataprovider.front.so /vendor/lib/libcam.metadataprovider.so
   adb shell 'chmod 644 /vendor/lib/libcam.metadataprovider.so; sync'
   adb shell 'stop cameraserver; stop camerahalserver; start camerahalserver; start cameraserver'
   adb shell dumpsys media.camera | grep Facing        # Facing: Front
   ```

2. Remove the line `<feature name="android.hardware.camera" />` (the back camera) from
   `/vendor/etc/permissions/android.hardware.camera.xml`, leaving `camera.front` and
   `camera.any`, so CameraX expects one camera rather than two. Reboot.

After the reboot `ha/screen_saver.py` (or the select entity) turns detection on, and the
binary sensor follows people in front of the display: on for 10 seconds per motion event.

Cost, measured: VACA goes from about 12% to about 75% of one core and the camera service
adds about 15% (the preview runs at 800x600) in the first minutes after boot. Twenty minutes
after boot it had settled to about 40% for VACA and 13% for the camera service, with two of
the four cores parked and those two about 45% busy; ping to Home Assistant stays in the tens
of milliseconds, unlike openWakeWord. The load average reads 7 or more regardless: this
kernel counts its own sleeping threads, so judge by `/proc/stat` instead. "face" mode was not
measured.

The sensor turns on for 5 to 10 seconds per motion event and off again, so with someone in
the room it flips every few seconds. That needs no debounce: every "on" restarts the idle
count, and the saver wants five minutes without one. The other side of that is that anything
in the camera's view that keeps moving (a fan, a window, a television) keeps the saver away
for as long as the room is bright. That happened here at VACA's default sensitivity of 70:
an hour without one five-minute gap, most of it with nobody there. Counted over four minutes
each: 10 events at 70, 4 at 40, none at 15, none in "face" mode (which costs more, VACA at
about 68% of a core against 40%). At 20 the saver started by itself after five quiet
minutes, but someone moving six feet away woke it, and the display should only react to a
touch, a voice command or someone right at it. Frame differencing cannot tell near from
far, so no sensitivity gives that (8 was tried). The camera therefore no longer ends a
saver at all: "Smart Display - Activity" ignores it while the saver is showing. It still
counts as activity while the dashboard is up, so the saver does not start with people moving
about the kitchen, and for that job seeing across the room is right: `MOTION_SENSITIVITY = 20`.
"Someone right at it" comes from the proximity sensor, step 17a.3a. Setting
`MOTION_MODE = "none"` would give the half core back, at the price of the saver starting
five minutes after the last touch whoever is in the room.

Dead end worth knowing: `NSCamCustomSensor::getSensorFacingDirection` in
`libcameracustom.so` looks like the place (a table of back, front, back) but changing it
does not change what Android reports. That file is back to the original.

**17a.2 Let auto-brightness and VACA move the backlight.** Out of the box VACA's brightness
and auto-brightness entities change nothing on this firmware: the app is not allowed to
write system settings.

```bash
adb shell appops set com.msp1974.vacompanion WRITE_SETTINGS allow
adb shell cat /sys/class/leds/lcd-backlight/brightness     # read the backlight, 0 to 255
```

After that, `switch.…_auto_brightness` off plus `number.…_screen_brightness` at 10, 1, 0 gave
backlight 25, 2, 0, and turning auto-brightness back on restored about 141. The setting
survives a reboot. The saver leaves brightness on automatic: by the curve in step 17 a dark
room gives a backlight of about 20 of 255, which with grey text is the dark clock's dimness.

**17a.3 Room light.** The display has an ambient light sensor (VCNL4200) that drives
auto-brightness, but it is an Android Things "dynamic" sensor and VACA does not see it.
Android's own smoothed reading is in `dumpsys display` (`mAmbientLux`, 0.05 s to read).
`device/lightsense.sh` reads it every 15 seconds and posts it to the local-only webhook
`kitchen_display_lux` when it changes by more than a quarter, and every 5 minutes regardless;
`device/lightsense.rc` starts it at boot, exactly like the volume watcher in step 16:

```bash
adb remount
adb push device/lightsense.sh /system/bin/lightsense.sh
adb push device/lightsense.rc /system/etc/init/lightsense.rc
adb shell 'chmod 755 /system/bin/lightsense.sh; chmod 644 /system/etc/init/lightsense.rc; sync'
adb reboot
```

In Home Assistant, "Smart Display - Light level" keeps `input_boolean.kitchen_display_dark`
in step: on below 3 lx, off above 8 lx, unchanged in between so it cannot flap. If no
reading has arrived for 15 minutes it uses the sun instead (dark when more than 4 degrees
below the horizon). After the reboot `getprop init.svc.lightsense` says `running` and the
first reading arrives within half a minute of boot. The thresholds were checked by posting
readings to the webhook by hand:

```bash
curl -X POST -H 'Content-Type: application/json' -d '{"lux": 1}' http://10.0.1.174:8123/api/webhook/kitchen_display_lux
```

**17a.3a Someone right at the display: the proximity sensor.** The same chip (VCNL4200, I2C
bus 2, address `0x51`) has an infrared proximity half, listed by `dumpsys sensorservice` as
"VCNL 4200 Proximity Sensor". Nothing uses it: it is a dynamic sensor like the light one, so
VACA's "Screen on with proximity" does not see it, there is no kernel driver or `/sys` entry
(Android Things' `peripheralman` drives the chip from user space), and its register
`PS_CONF1` reads 1, shut down. The display has no i2c tools either, so
`device/src/proxsense.c` is a small static program that talks to `/dev/i2c-2` itself. It
switches proximity on at the chip's longest reach (9T integration, 8 pulses, 200 mA LED,
16-bit output; registers 3 = `0x080a`, 4 = `0x0760`), leaves the light sensor's registers
alone (auto-brightness went on working), reads the count five times a second, and prints a
line when it rises `DELTA` above the resting level for two readings in a row, then every 30
seconds while it stays there. `device/proxsense.sh` posts each line to the local-only webhook
`kitchen_display_near`, a trigger of "Smart Display - Activity".

Measured here with a person facing the display: resting 38 (34 to 43), about 56 at three
feet, about 195 at arm's length, 1100 to 1300 for a hand six inches away, nothing at six
feet. `DELTA=60` puts the line at roughly two feet. The resting level is followed slowly, and
anything that stays in front for two minutes becomes the new resting level, so an object left
on the counter cannot hold the display awake. It works the same in the dark. Cost: about
0.03% of a core.

```bash
nix shell nixpkgs#zig -c zig cc -target arm-linux-musleabihf -static -Os -s -o work/proxsense device/src/proxsense.c
adb remount
adb push work/proxsense /system/bin/proxsense
adb push device/proxsense.sh /system/bin/proxsense.sh
adb push device/proxsense.rc /system/etc/init/proxsense.rc
adb shell 'chmod 755 /system/bin/proxsense /system/bin/proxsense.sh; chmod 644 /system/etc/init/proxsense.rc; sync'
adb reboot
```

After the reboot `getprop init.svc.proxsense` says `running`. To see the readings and pick
another `DELTA`: `adb shell 'stop proxsense; proxsense raw'`, then `start proxsense`. To test
without standing there:

```bash
curl -X POST -H 'Content-Type: application/json' -d '{"counts": 200, "rest": 38}' http://10.0.1.174:8123/api/webhook/kitchen_display_near
```

**17a.4 Photos.** `$AVB_PYTHON ha/photo_album.py` (needs SSH to Home Assistant):

- creates `input_text.kitchen_display_album_url`. **This is the one setting**: paste a shared
  Google Photos album link (album > Share > Create link) into the helper "Kitchen display
  photo album link". It lives only in Home Assistant; do not put a real link in the script
  if the script goes into a public repository. Empty, or anything that is not a
  `photos.app.goo.gl` or `photos.google.com` link, means placeholder photos from picsum.photos;
- copies `ha/album_sync.py` to `/config/kitchen_display/` and writes
  `/config/packages/kitchen_display.yaml`, a command-line sensor
  (`sensor.kitchen_display_album`, state = number of photos, attributes `source`, `updated`,
  `error`) that runs the sync every 6 hours. `configuration.yaml` needs
  `homeassistant: packages: !include_dir_named packages`, and Home Assistant needs one
  restart the first time (check the config first; later changes take `command_line.reload`);
- creates "Smart Display - Refresh photo album", which syncs at once when the link changes.

Google's Photos Library API no longer lists albums an app did not create, so the sync reads
the public share page, which carries each picture's `lh3.googleusercontent.com/pw/…` address
and size, and downloads each one once at 1024 px into `/config/www/kitchen_display/`. The
display loads them from Home Assistant at `/local/kitchen_display/`, so it needs no internet
access. Pictures removed from the album are deleted on the next sync; if the album cannot
be read, the copies already there stay. With a real album of 302 pictures the page listed
all 302; the sync keeps the first 300 (`MAX_PHOTOS`), about 45 MB, and the first run took
under three minutes.

Two things to know. `/local/` is served **without login** to anything that can reach Home
Assistant on port 8123, so anyone on the home network who knows the address can fetch these
pictures. And a share page lists only the first few hundred items of an album.

**Gotcha.** A `pattern` on the `input_text` helper (to restrict it to share links) left the
helper `unavailable` after a Home Assistant restart. The check is in the sensor's command
template instead, which is also the right place for it: the link is passed to a shell.

**17a.5 The view and the card.** `ha/build_smart_display.py` adds a panel view `saver` that
is not in the navigation row; rebuild and save the dashboard as in step 11. Its one card,
`custom:kitchen-saver-card`, is `ha/frontend/kitchen_saver.js`, with two faces chosen by
`dark_entity`:

- bright: two stacked images that crossfade every 20 seconds (only opacity is animated,
  which this GPU handles), landscape pictures filling the screen and portrait ones fitted
  on black; over them the time and date in white with a soft dark halo so they read on any
  picture, jumping to another corner with every picture;
- dark: no pictures, the time at 150 px in dim grey on black, gliding to a random new
  position once a minute.

The same file reports touches on every view of the display (user agent check, at most one
report per 20 seconds).

**17a.6 The automations.** `$AVB_PYTHON ha/screen_saver.py` registers the card as a
dashboard resource (a `data:` URL, so no file has to be copied into Home Assistant), creates the helpers and three automations:

- **Smart Display - Activity** presses `input_button.kitchen_display_activity` when the
  proximity sensor reports someone close, the voice satellite changes state (the wake word
  does that), the volume changes, the display changes view (except to the saver), or the
  camera sees motion. The card presses the same button on touch. "Idle" is then one
  question: how long since that button was pressed. The camera is ignored while the saver is
  showing, because it sees movement across the whole room and the saver should only give
  way to someone using the display; and while the room is dark, because noise in a dark
  picture reads as motion.
- **Smart Display - Screen saver** starts when the button has been quiet for 5 minutes, the
  camera sees nobody, the satellite is idle, View Assist is in its normal mode and no camera
  takeover is showing. It remembers the current view (the display's own
  `sensor.vaca_…_current_path`, so a tab opened by touch counts) in
  `input_text.kitchen_display_saver_return`, opens the saver with
  `view_assist.navigate … revert_timeout: 0` (so View Assist's 20 second view timeout leaves
  it alone, with no mode change), then waits for the button or for the view to change, and
  navigates back only if the display is still on the saver.
- **Smart Display - Light level**, described in 17a.3.

Things that had to be handled:

- **A camera takeover that starts on the saver hands the screen back to the saver.** The
  saver automation's run ended when the takeover took the screen, so it picks a showing saver
  up again (template trigger) and re-sends the navigation with `revert_timeout: 0`. The return
  view is not overwritten.
- **Reloading the automation or restarting Home Assistant kills a running saver.** The same
  pick-up trigger, plus one on Home Assistant start, resumes it. If a touch arrives while
  nothing is listening, the card asks View Assist to go home itself after 4 seconds.

Measured on the display: the saver costs the same as the Home view (WebView renderer about
25% of one core). To test, set `SAVER_MINUTES` to 1 and run the script; force the dark face
with the webhook above; `adb shell input tap 500 300` is a touch.

An earlier version dimmed and then switched the backlight off after 30 minutes
(brightness 0 through VACA is backlight off with Android awake, and a touch still lands on
the page). It worked, but a dark clock was preferred to a dead screen.

---

## 18. Problems hit and how each was diagnosed

| Symptom | Cause | Fix | How it was found |
|---|---|---|---|
| Fastboot never appears | Volume + released too early | Hold 15 s | Watching USB re-enumerate in the same mode |
| Garbled fastboot replies | Commands sent back to back | 1 s between commands | Clean when slowed down |
| Google package disables lost after reboot | Rebooted before Android saved them | Wait 15 s, check `pm list packages -d` | Compared before and after |
| Kiosk app did not start at boot | It had been force-stopped; stopped apps get no boot broadcast | Launch it once before rebooting | `dumpsys package … stopped=true` |
| WebView would not fit in `/system` | Filesystem reserve | Install as a user app | `adb push` error |
| `homeassistant.local` unreachable | No mDNS resolver on Android 8.1 | Hosts entry | `ping` on device vs Mac |
| Wake word heard only sometimes | Threshold 6 vs score 0.64 | Threshold 5, chime on | `logcat` line "wake word detected at 0.64, threshold is 0.6" |
| "Speech-to-text failed" after wake word | VACA's audio stream went malformed after mic gain was changed live | Restart the app; set gain, then restart | Cloud STT error was "400 Invalid HTTP request", while silence and noise sent directly gave "No text recognized" |
| "Unable to connect to Home Assistant" on the display | openWakeWord used 262% CPU and starved Wi-Fi (gateway ping 300 to 700 ms) | microWakeWord (CPU about 15 to 19%, ping about 10 ms) | `top` and `ping` on the device, before and after |
| Timers set by voice but invisible | Built-in satellite timers have no UI | View Assist timers blueprint | `sensor.den_display` `timers` attribute empty |
| View Assist screens say "Configuration error" | Missing button-card, layout-card, card-mod | Install from HACS | Card types in the dashboard config |
| Sports phrases not understood | Blueprint has four fixed phrasings | Extend the phrase list | Pipeline debug showed what was heard |
| Generic score request reports the wrong team | Shared tracker keeps the last team | Default-team automation | Tested after asking about another team |
| Camera tiles broken on the main Overview | 3 of 4 high-resolution camera entities were unavailable in Home Assistant; high-res streams are also beyond the decoder | Medium resolution entities | Entity states; WebRTC "No decodable frame" in `logcat` |
| Live camera freezes after 20 to 30 seconds, then moves a frame every few seconds | WebRTC over UDP loses about 1 packet in 5 on the display's Wi-Fi link and Home Assistant's WebRTC server does not resend | `ha/frontend/hls_only.js`: the display asks for HLS only (step 11, "Live video") | WebRTC statistics through the remote debugger (`packetsLost`, `framesDecoded` stuck while bytes kept arriving); two screenshots 5 s apart showed the same frame |
| Camera grid used half a core more with Advanced Camera Card than with stock cards | The card's snapshot provider fetched the full camera frame (1.3 MB) for each tile | `image.entity_parameters: width=480&height=270` | Remote debugger network log |
| Full-screen camera card left a 56 px band at the bottom | In a panel view the card subtracts the header height, and the header is hidden on the display | `view.theme.overrides: {"--kiosk-header-height": "0px"}` | Element sizes through the remote debugger |
| Camera takeover returned to Home instead of the previous view | View Assist goes to its home screen on a mode change, and that landed after the automation's own navigate | Restore the mode, wait 1 s, then navigate | History of `sensor.vaca_…_current_path` showed the right view for under a millisecond |
| Camera entities flip to `unavailable` after a live view | Home Assistant 2026.10.0 ships FFmpeg 9, which rejects Protect's self-signed RTSPS certificate, so the HLS stream worker fails for every camera; WebRTC on the display still works | Update to 2026.10.1 or later (done 2026-10-11; the reload automation used in between is retired) | `system_log/list`; requesting `camera/stream` for a healthy camera broke it too; `ffmpeg -i rtsps://…` printed "Peer certificate failed verification"; core issue 184775 |
| Camera snapshots blank on the display (grey tiles, broken-image icons) | Same 2026.10.0 bug: each live view leaves two HLS playlist requests hanging, and six fill the browser's connection limit | Update to 2026.10.1 or later (done 2026-10-11; the HLS guard resource used in between is retired); restart the app to clear it once | WebView remote debugger network trace; `netstat` on the device; the same URL answered `curl` instantly |
| Music "playing" but silent | IoT VLAN could not reach Music Assistant's stream port 8097 | Firewall rule | `logcat` showed the stream URL; `curl` to 8097 from the device returned nothing |
| Rocker not loud enough | Android media stream was at 40 of 100 underneath the player's volume | Drive the stream itself | `dumpsys audio` |
| Rocker steps uneven | Android's volume curve | 3 dB table | `dumpsys media.audio_policy` |
| AI retracted real actions | Local replies look like unbacked claims to it; it had no music tool | Prompt and a music script | Screenshot of its reply |
| VACA motion detection never reports | Camera HAL says the only camera faces back; VACA wants a front camera | One-byte patch to the camera's static metadata and a feature-file edit, step 17a.1 | `logcat` CameraX lines; `dumpsys media.camera` |
| Album link helper `unavailable` after a restart | It had a `pattern` | Recreate without it; check the link in the command template | Entity state showed `restored: true` |
| VACA brightness entities do nothing | App may not write system settings | `appops set … WRITE_SETTINGS allow` | Backlight sysfs value did not move; `appops get` showed a reject |
| Display went to Home, not the tab it was on, after a camera takeover, the saver or a voice answer | Return points came from View Assist's `current_path`, which only follows `view_assist.navigate` and never sees a tab opened by touch; and View Assist closes its answer views to Home | Read `sensor.vaca_…_current_path` instead, return with `revert_timeout: 0`, and `ha/tab_return.py` for answer views | History of both sensors side by side: Music by touch at 00:16, takeover at 00:19, Home at 00:20 |
| Wake word fired on random speech | Threshold 5 (below the default) | Threshold 6 | Pipeline debug runs: 5 of 7 in a day ended `stt-no-text-recognized` |
| Screen hopped between cameras as one person walked up | Each camera's detection restarted the takeover on its own view | Only the doorbell takes the screen from another camera; 120 s cooldown for the others | Automation logbook: 86 triggers, 28 episodes in a day |
| Saver went home 20 s after a camera takeover handed back | The takeover navigates with the normal view timeout | Saver re-sends its navigation with `revert_timeout: 0` | `current_path` history |
| Screen flipped to portrait | The orientation had been forced by the earlier kiosk app | VACA orientation = landscape | Screenshot was 600x1024 |
| Force-stopping VACA dropped Wi-Fi for 15 s | The app holds the Wi-Fi lock | Avoid, or expect it | `wpa_supplicant` log: "reason=3 locally_generated=1" |

Diagnostic commands worth keeping:

```bash
# what did the display hear, and what was answered (last 6 voice runs)
nix develop --command sh -c 'P=<pipeline id>; for R in $($AVB_PYTHON ha/ha_ws.py call "{\"type\":\"assist_pipeline/pipeline_debug/list\",\"pipeline_id\":\"$P\"}" | jq -r ".pipeline_runs[-6:][].pipeline_run_id"); do $AVB_PYTHON ha/ha_ws.py call "{\"type\":\"assist_pipeline/pipeline_debug/get\",\"pipeline_id\":\"$P\",\"pipeline_run_id\":\"$R\"}" | jq -r ".events[] | select(.type==\"stt-end\" or .type==\"intent-end\" or .type==\"error\") | \"\(.type) \(.data|tostring|.[0:200])\""; done'
# VACA's own log
adb -s HA0000XX shell 'logcat -d | grep " $(pidof com.msp1974.vacompanion) " | grep -vE "GLConsumer|zygote|chromium" | tail -40'
# load and network health on the device
adb -s HA0000XX shell 'top -b -n 1 | head -12; ping -c 5 -i 0.3 <gateway>; cat /proc/loadavg'
# Home Assistant's error log, filtered
nix develop --command sh -c '$AVB_PYTHON ha/ha_ws.py call "{\"type\":\"system_log/list\"}"' | jq -r '.[] | "\(.level) \(.name): \(.message|tostring|.[0:300])"'
# Music Assistant add-on log
python3 ha/ha_rest.py GET /api/hassio/addons/d5369777_music_assistant/logs | tail -40
```

---

## 19. Verification checklist

Run these after a rebuild or a reboot.

```bash
nix develop --command sh -c '
A="adb -s HA0000XX"
$A shell "getprop init.svc.volkeys"                                  # running
$A shell "dumpsys webviewupdate | grep \"Current WebView\""          # 138.0.7204.63
$A shell "pm list packages -d | wc -l"                               # 7 (six Google packages and Fully)
$A shell "dumpsys activity activities | grep mResumedActivity"       # com.msp1974.vacompanion
$A shell "curl -s -o /dev/null -m 6 -w \"%{http_code} %{time_total}s\n\" http://10.0.1.174:8123/manifest.json"   # 200, well under 1 s
$A shell "curl -s -o /dev/null -m 6 -w \"%{http_code}\n\" http://10.0.1.174:8097/"                               # 404 (reachable)
$A shell "top -b -n 1 | sed -n 4p"                                    # mostly idle
$AVB_PYTHON ha/ask.py "set a timer for 1 minute" "show me my timers" "how are the seahawks doing" "show me the front driveway" "go home" "what is the tallest mountain in Washington state" "how do I make peach cobbler"'   # the last one names a site and notifies the phone
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://10.0.1.174:8123/api/webhook/den_display_volume_up   # 200, volume moves one position
```

Then simulate a detection as in step 11 ("Camera on detection or doorbell"): a still of
the camera should fill the screen within a second or two, the live picture follow within
about 10 seconds, and the previous view come back about 30 seconds after the sensor is set
to off.

Screen saver: `adb shell dumpsys media.camera | grep Facing` says Front and
`binary_sensor.…_motion` turns on when you wave at the display. Leave it alone for five
minutes: slideshow with a clock (or the dark clock at night). Walking past it changes
nothing; stepping up to it, the wake word, or `adb shell input tap 500 300` brings back the
previous view.

Then by voice at the display: "Okay Nabu, set a timer for one minute", "Okay Nabu, play
some Fleetwood Mac", and press the rocker.

Confirmed to survive a reboot: all volume levels, the button watcher, wake word settings,
the main screen, disabled packages. Not yet confirmed across a reboot: the brightness
setting in step 17.

---

## 20. Going back

- **Fully Kiosk instead of VACA:** `adb shell pm enable de.ozerov.fully`, launch it, and
  force-stop VACA. Fully's settings live in
  `/data/data/de.ozerov.fully/shared_prefs/de.ozerov.fully_preferences.xml`.
- **Stock WebView:** `downloads/backup/stock-webview-66.0.3359.158.apk` is the original.
- **Re-enable a Google package:** `adb shell pm enable <package>`.
- **Stop cameras taking over the screen:** disable or delete the "Smart Display - Show
  camera on detection or doorbell" automation and the
  `input_text.den_display_takeover_return` helper.
- **Back to WebRTC:** `$AVB_PYTHON ha/hls_only.py remove` and reload the display's page.
- **Back to the stock camera cards:** the generator, takeover and voice scripts from before
  the Advanced Camera Card change are in the git history (commit `b1b394f`); rebuild the
  dashboard and rerun `ha/camera_takeover.py` and `ha/camera_voice.py` from those. The
  card itself can stay installed or be removed in HACS.
- **Remove the screen saver:** `$AVB_PYTHON ha/screen_saver.py remove` (automations, card
  resource, camera detection off), delete the `saver` view from `ha/build_smart_display.py`
  and rebuild, delete the `kitchen_display` helpers and the "Refresh photo album"
  automation, and on Home Assistant delete `/config/packages/kitchen_display.yaml`,
  `/config/kitchen_display/` and `/config/www/kitchen_display/`, then restart it.
  On the display: push the two originals from `downloads/backup/` back to `/vendor`
  (step 17a.1), delete `/system/bin/lightsense.sh`, `/system/bin/proxsense`,
  `/system/bin/proxsense.sh` and the `lightsense.rc` and `proxsense.rc` files in
  `/system/etc/init/`, and `adb shell appops set com.msp1974.vacompanion WRITE_SETTINGS default`.
- **Remove the button watcher:** delete `/system/bin/volkeys.sh` and
  `/system/etc/init/volkeys.rc`, and the "Smart Display - Volume buttons" automation.
- **Stock firmware:** flash the user build to the active slot and relock AVB with
  `fastboot oem at-lock-vboot`. The thread warns the order matters. Its
  `UserImageFlash.cmd` relocks at the end and people have ended up in a red-state boot
  until unlocking again. Google's update servers are gone, so first-time setup may hang
  at "Updating 0%". This was not attempted here.
- **Firewall:** the previous state of each changed rule is noted in
  `~/.local/state/unifi-mcp/skills/firewall-snapshots/`.

---

## Appendix A: values specific to this build

| What | Value here |
|---|---|
| Display serial | `HA0000XX` |
| Display Wi-Fi MAC | `aa:bb:cc:dd:ee:01` |
| Display IP (reserved) | `192.168.9.253` on IoT VLAN `192.168.8.0/23`, gateway `192.168.8.1` |
| Home Assistant | `http://10.0.1.174:8123`, version 2026.10.1 |
| Admin computer wired MAC | `aa:bb:cc:dd:ee:02` |
| VACA device name / id suffix | `vaca_ha0000xx` |
| View Assist device entity | `sensor.den_display` (named "Kitchen display") |
| Phone notify service | `notify.mobile_app_your_phone` |
| VACA device id (for `ask.py`) | `549c40def793d18c19283c0859c88c68` |
| Voice pipeline id | `01hmmxp6jjc996mawjb5xzepfg` ("Home Assistant Cloud") |
| Music Assistant config entry | `01M4HGGHSCR4A11QKH597KY6KP` |
| Music player entity | `media_player.vaca_ha0000xx_media_player_2` |
| View Assist "Kitchen display" entry | `01M4HF6Y2MTWS5BRJFANZTX1YZ` |
| Anthropic entry / conversation subentry | `01M4HGNSMY8B0C54JP827YY0FJ` / `01M4HGNSMYM66CB3PQENA3K3ZZ` |
| Volume GPIOs | 429 up, 576 down |
| UniFi policies | "Allow admin Mac to Smart Display adb", "Block Internal to Smart Display adb", "Allow IOT to Home Assistant" |

Ids like the pipeline and config entries are generated per install. Find yours with
`assist_pipeline/pipeline/list`, `config_entries/get` and `config/device_registry/list`.

## Appendix B: versions and file hashes

| Component | Version |
|---|---|
| Firmware flashed | Android Things 8.1.0, `OIMC.190719.013/5813256`, userdebug |
| nixpkgs | `39ad350a0602fa0a58a544344e3e9187526ea45c` (nixpkgs-unstable, 2026-10-07) |
| android-tools | 37.0.0 |
| Home Assistant | 2026.10.1 (built on 2026.10.0) |
| View Assist Companion App | 0.13.5 (app and integration; installed as 0.13.4, updated 2026-10-11) |
| View Assist integration | 2026.7.0 |
| TeamTracker / card | 0.18.4 / 0.17.2 |
| button-card / layout-card / card-mod | 7.0.1 / 2.4.7 / 4.2.1 |
| Advanced Camera Card | 8.1.0 |
| Music Assistant add-on | 2.10.6 |
| WebView | LineageOS 138.0.7204.63 (arm) |
| Simple Keyboard | version code 148 (6.7) |
| Fully Kiosk Browser (disabled) | 1.61.4 |

SHA-256:

```
525dcd80087999da41a7ef516f8c4d89173112a5fca3de9df78d1038952a6fcf  Ivy-full-flash-15.42.1-1.1.05813256-US.zip
8e2ae30844961614cff7e4aeb1ed0d4d08d1f617aaf27d0835b79ed91d0c8be3  Lenovo-Android-Things-avb-unlock.zip
b7268786318f404bdad53eaaec889619ff30100b935541a9e393e32efed3cf11  lineage-webview-138.0.7204.63-arm.apk
b8affd986041afc9f47f59a3b5953b791a06401fb77682cff551ed4d68c32885  simple-keyboard-148.apk
e4708acf99ab2b162373708bf8b122e3c387c5062a3e136356ef941df6868d2f  vaca-0.13.5.apk
8769df7bca33c14254a58049a825cf58d3dd7b3272156225662bb4810b9f8f8d  vaca-0.13.4.apk (the version first installed)
42df2da1ef35074611159e1b07c7d16a442ba72079b652d1dd7d5168aa43dec7  fully-kiosk-1.61.4.apk
2064adcf5e17a374857881f2aa4a055b741be0342fa8f5c852859946319ce3cd  stock-webview-66.0.3359.158.apk (pulled from the device)
```

## Appendix C: sources

- **XDA thread** (procedure, firmware and unlock tool links, later posts on WebView 138,
  wireless adb, package names, bricks):
  <https://xdaforums.com/t/cd-17302f-lenovo-smart-display-7-ivy-avb-bootloader-unlock-firmware.4472041/>
  by deadman96385. Useful later posts: adde r2 (kiosk app, disabling
  `com.google.assistant.core`), mlrtime3 (10-inch notes, `persist` adb, button timing),
  jarek_krk (replacing the WebView with LineageOS 138, `UserImageFlash.cmd` relocking AVB),
  RYuhMine (Google's OTA buckets are gone).
- **Firmware and unlock tool** (linked from that post):
  `https://s3.us-east-1.wasabisys.com/filestash-buk/lenovo-solutions/Ivy-full-flash-15.42.1-1.1.05813256-US.zip`,
  `…/Ivy-user-15.42.1-1.1.0.5813256-US.zip`, `…/Ivy-debug-15.42.1-1.1.0.5813256-US.zip`,
  `…/Lenovo-Android-Things-avb-unlock.zip`
- **`at_auth_unlock.py`**: Android Open Source Project, Apache 2.0, included in the unlock zip.
- **LineageOS WebView prebuilt (arm)**:
  <https://github.com/LineageOS/android_external_chromium-webview_prebuilt_arm>, commit `b2639126d0`.
- **Simple Keyboard**: <https://f-droid.org/packages/rkr.simplekeyboard.inputmethod/>
- **View Assist Companion App**: <https://github.com/msp1974/ViewAssist_Companion_App>
  and its wiki (Getting Started, Configuration Options, Wake Word Detection & Voice
  Recognition, Troubleshooting).
- **View Assist**: <https://github.com/dinki/View-Assist> (blueprints under
  `View_Assist_custom_sentences/`) and <https://github.com/dinki/view_assist_integration>.
- **TeamTracker**: <https://github.com/vasqued2/ha-teamtracker>,
  <https://github.com/vasqued2/ha-teamtracker-card>.
- **Frontend cards**: <https://github.com/custom-cards/button-card>,
  <https://github.com/thomasloven/lovelace-layout-card>,
  <https://github.com/thomasloven/lovelace-card-mod>.
- **Advanced Camera Card**: <https://card.camera>,
  <https://github.com/dermotduffy/advanced-camera-card> (live providers, the
  `low-performance` profile, per-camera `image` options).
- **Music Assistant**: <https://www.music-assistant.io/>. Reports of Spotify playlist
  problems after Spotify's February 2026 API change:
  <https://github.com/music-assistant/support/issues/5114>,
  <https://github.com/music-assistant/support/issues/4978>.
- **Fully Kiosk Browser** (used briefly): <https://www.fully-kiosk.com/>
- **Anthropic console** for the API key: <https://console.anthropic.com>
- **Test stream**: SomaFM Groove Salad, `https://ice1.somafm.com/groovesalad-128-mp3`.

## Appendix D: what was tried and abandoned

- **Fully Kiosk Browser as the main screen.** Installed, pointed at Home Assistant by
  editing its preferences XML as root (`startURL`, `launchOnBoot`, `forceScreenOrientation`
  = 2 for landscape), and it worked. Dropped when VACA turned out to cover the dashboard,
  voice and music for free. Fully's Remote Admin and JavaScript injection are paid "PLUS"
  features that put a watermark on the screen without a licence (8.90 EUR). It is
  disabled, not removed, because VACA's documentation warns the two compete for the microphone.
- **Dark mode by injected JavaScript** in Fully (setting Home Assistant's `selectedTheme`
  in localStorage). It worked but triggered the PLUS watermark. VACA has a dark mode switch.
- **Putting the WebView in `/system`.** Out of space (step 6).
- **openWakeWord.** Too heavy for this CPU (step 18).
- **Chromecast.** Not functional on this firmware.
- **Changing volume on the device** with `media volume`, `input keyevent` or
  `service call audio`. Too slow, 1% steps, or no effect (step 16).
- **`seclabel u:r:su:s0` for an init service.** Denied by SELinux (step 16).
- **A separate automation for generic sports phrases.** It raced with the blueprint, whose
  reply won. Replaced by the default-team automation (step 12b).
- **View Assist's camera blueprint.** Its catch-all phrase pattern conflicts with other
  "show me …" phrases (step 12c).
- **Timed recordings to catch button presses.** They kept missing the presses. A recorder
  that waits for the first change worked.
