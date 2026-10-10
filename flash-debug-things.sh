#!/usr/bin/env bash
# Shell port of ToDebugThings.cmd from the XDA Ivy firmware zip.
# User firmware (with adb) -> slot A, debug firmware -> slot B, boot slot A.
# Requires: device in fastboot, bootloader unlocked, AVB unlocked.
# Run inside `nix develop`. Stops at the first failed command.
set -euo pipefail

FW="${1:-downloads/fw}"
A="$FW/A_Debug"
B="$FW/B_User"

fb() {
  echo "\$ fastboot $*"
  fastboot "$@"
  sleep 1 # this bootloader garbles replies when commands arrive back to back
}

state=$(fastboot getvar at-vboot-state 2>&1 | grep 'avb-locked' || true)
if [[ "$state" != *"avb-locked: 0"* ]]; then
  echo "AVB is not unlocked ($state). Refusing to flash." >&2
  exit 1
fi
sleep 1

fb flash boot0     "$B/boot0.img"
fb flash partition "$B/partition-table.img"
fb flash tee_b     "$B/tee.img"
fb flash tee_a     "$B/tee.img"
fb flash lk_b      "$B/lk.img"
fb flash lk_a      "$B/lk.img"
fb erase misc

fb flash boot_b    "$A/boot.img"
fb flash boot_a    "$B/boot.img"
fb flash system_b  "$A/system.img"
fb flash system_a  "$B/system.img"
fb flash vendor_b  "$A/vendor.img"
fb flash vendor_a  "$B/vendor.img"

fb flash logo      "$B/logo.img"

fb flash oem_b     "$A/oem_mt8167s_sp2.img"
fb flash oem_a     "$B/oem.img"
fb flash vbmeta_b  "$A/vbmeta_mt8167s_sp2.img"
fb flash vbmeta_a  "$B/vbmeta.img"

fb flash oem_bootloader_b "$A/oem_bootloader_mt8167s_sp2.img"
fb flash oem_bootloader_a "$B/oem_bootloader.img"

# at_write_persistent_digest --name factory --clear_digest
# (staged blob: u32le name length, name, u32le digest length 0)
digest=$(mktemp)
name='avb.persistent_digest.factory'
printf "$(printf '\\x%02x' "${#name}")"'\0\0\0%s\0\0\0\0' "$name" > "$digest"
fb stage "$digest"
fb oem at-write-persistent-digest
rm -f "$digest"
fb flash factory   "$B/factory.img"

fb set_active a

fb reboot bootloader
sleep 8

fb format userdata

echo "FLASH COMPLETE. Device left in fastboot; run 'fastboot reboot' to boot."
