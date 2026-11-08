#!/bin/bash
# Drive the entry-probe bisection of the iOS 27 XNU on shennong without a photo.
#
# Each image stops the kernel at one _arm_init milestone by issuing a PSCI
# SYSTEM_RESET there. A boot that reaches its probe comes back to recovery (or
# fastboot) on its own, so the answer is a USB event the host can see; a boot
# that never reaches its probe leaves the phone hung with no USB and needs a
# manual power cycle. Probing from the earliest milestone forward therefore
# costs at most one manual reset (the first miss).
#
# Usage: run.sh [first-index] [last-index]
#   The images are C:\Users\yoox\AppData\Local\Temp\Mu-probe-<n>.img and the
#   milestone each one probes is listed in built.txt next to this script.
set -u
WIN=/mnt/c/Windows/System32/cmd.exe
FB='D:\Dev\Android\WindowsTools\platform-tools\fastboot.exe'
ADB='D:\Dev\Android\WindowsTools\platform-tools\adb.exe'
WIN_TMP='C:\Users\yoox\AppData\Local\Temp'
HERE=$(cd "$(dirname "$0")" && pwd)
LOG="$HERE/run.log"

log() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }

run() {  # run(cmdline, timeout-seconds)
  timeout "${2:-40}" /init "$WIN" /c "$1" 2>/dev/null | tr -d '\r\000'
}

fb_state() { run "$FB devices" 25 | grep -a 'fastboot$' | head -1; }
adb_state() { run "$ADB devices" 25 | grep -aE '(recovery|device)$' | head -1; }

ensure_fastboot() {
  local i state
  for i in $(seq 1 24); do
    [ -n "$(fb_state)" ] && return 0
    state=$(adb_state)
    if [ -n "$state" ]; then
      log "device is '$state'; rebooting to the bootloader"
      run "$ADB reboot bootloader" 30 >/dev/null
      sleep 8
    else
      sleep 5
    fi
  done
  log 'ERROR: the device never reached fastboot'
  return 1
}

boot_probe() {  # boot_probe(index) -> 0 reached (reset seen), 1 not reached (hung)
  local n=$1 i
  log "probe $n: fastboot boot Mu-probe-$n.img"
  run "$FB boot $WIN_TMP\\Mu-probe-$n.img" 180 | grep -aE 'OKAY|FAILED' | head -2 | while IFS= read -r l; do log "  $l"; done
  for i in $(seq 1 36); do
    sleep 10
    if [ -n "$(adb_state)" ]; then
      log "probe $n: HIT - the device reset and came back on ADB"
      return 0
    fi
    if [ -n "$(fb_state)" ]; then
      log "probe $n: HIT - the device reset and landed in fastboot"
      return 0
    fi
  done
  log "probe $n: MISS - no reset in six minutes, the phone is hung and needs a power cycle"
  return 1
}

first=${1:-1}
last=${2:-13}
mkdir -p "$HERE"
: > "$LOG"
log "bisection from probe $first to $last"
for n in $(seq "$first" "$last"); do
  ensure_fastboot || exit 1
  if ! boot_probe "$n"; then
    log "stopping: the stop lies before the milestone of probe $n (see built.txt)"
    exit 2
  fi
  log "probe $n reached; next"
done
log "all probes reached: the kernel got past every listed milestone"
