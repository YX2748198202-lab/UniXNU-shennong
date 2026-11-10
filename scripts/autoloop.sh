#!/bin/bash
# Whenever the phone shows up in fastboot, boot the newest image in boot/ that
# has not been booted yet.  State lives in .autoloop-last so a device that
# resets back into fastboot does not replay the same build forever.
BOOT=/home/yoox/android/artifacts/UniXNU-shennong/boot
RUN=/home/yoox/android/artifacts/UniXNU-shennong/device-runs/2026-11-11
LOG=$RUN/autoloop.log
STATE=$RUN/.autoloop-last
while true; do
  if timeout 6 fastboot devices 2>/dev/null | grep -q fastboot; then
    IMG=$(ls -t "$BOOT"/Mu-shennong-fd*.img 2>/dev/null | head -1)
    if [ -n "$IMG" ]; then
      HASH=$(sha256sum "$IMG" | cut -d' ' -f1)
      if [ "$(cat "$STATE" 2>/dev/null)" != "$HASH" ]; then
        echo "$(date +%H:%M:%S) boot $(basename "$IMG") ${HASH:0:8}" >>"$LOG"
        timeout 120 fastboot boot "$IMG" >>"$LOG" 2>&1
        echo "$(date +%H:%M:%S) issued exit $?" >>"$LOG"
        echo "$HASH" >"$STATE"
      fi
    fi
    sleep 15
  fi
  sleep 9
done
