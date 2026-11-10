#!/bin/bash
# Wait for the phone to show up in fastboot, then boot the image once.
# Usage: wait-and-boot.sh <image> [minutes]
set -u
IMG=${1:?image path}
LIMIT=${2:-240}
LOG=/home/yoox/android/artifacts/UniXNU-shennong/device-runs/2026-11-10/wait-and-boot.log
for ((i = 0; i < LIMIT * 4; i++)); do
  if timeout 6 fastboot devices 2>/dev/null | grep -q fastboot; then
    echo "$(date +%H:%M:%S) device found, booting $(basename "$IMG")" >>"$LOG"
    timeout 120 fastboot boot "$IMG" >>"$LOG" 2>&1
    echo "$(date +%H:%M:%S) boot issued, exit $?" >>"$LOG"
    exit 0
  fi
  sleep 15
done
echo "$(date +%H:%M:%S) gave up after ${LIMIT} min" >>"$LOG"
exit 1
