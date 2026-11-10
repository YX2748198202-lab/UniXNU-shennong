#!/bin/bash
# Whenever the phone shows up in fastboot, boot the newest image in boot/.
# Keeps the experiment loop going without anyone watching.
BOOT=/home/yoox/android/artifacts/UniXNU-shennong/boot
LOG=/home/yoox/android/artifacts/UniXNU-shennong/device-runs/2026-11-10/autoloop.log
while true; do
  if timeout 6 fastboot devices 2>/dev/null | grep -q fastboot; then
    IMG=$(ls -t "$BOOT"/Mu-shennong-fd*.img 2>/dev/null | head -1)
    if [ -n "$IMG" ]; then
      echo "$(date +%H:%M:%S) boot $(basename "$IMG")" >>"$LOG"
      timeout 120 fastboot boot "$IMG" >>"$LOG" 2>&1
      echo "$(date +%H:%M:%S) issued exit $?" >>"$LOG"
    fi
    sleep 20
  fi
  sleep 9
done
