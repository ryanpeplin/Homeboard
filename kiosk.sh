#!/bin/sh
# Starts Chromium fullscreen on the Pi's screen and restarts it if the board
# stops checking in with the server (Chromium can hang while starting during boot
# on a 512MB Pi, leaving a black screen). Launched from ~/.config/labwc/autostart.

URL=http://localhost:8080
LOG=/home/pi/chromium-boot.log
STARTUP_GRACE=180  # seconds a fresh Chromium gets to load the board
STALE_AFTER=180    # seconds without a check-in before Chromium is restarted

# The desktop doesn't pass these to startup programs on this Pi.
export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/1000

until curl -s "$URL/api/kiosk" >/dev/null; do sleep 2; done
sleep 20  # let the rest of the boot settle

while true; do
  echo "=== $(date) starting chromium" >> "$LOG"
  chromium --ozone-platform=wayland --no-memcheck --password-store=basic \
    --kiosk --incognito --renderer-process-limit=1 --no-first-run \
    --disable-extensions --disable-sync --disable-component-update \
    --disable-background-networking --disable-features=Translate,MediaRouter,OptimizationHints \
    --noerrdialogs --disable-infobars --check-for-update-interval=31536000 \
    --enable-logging=stderr "$URL" >> "$LOG" 2>&1 &

  sleep "$STARTUP_GRACE"
  while true; do
    age=$(curl -s "$URL/api/kiosk" | grep -o '[0-9][0-9]*')
    if [ -z "$age" ] || [ "$age" -gt "$STALE_AFTER" ]; then
      echo "=== $(date) board not checking in (last seen: ${age:-never}s ago), restarting chromium" >> "$LOG"
      break
    fi
    sleep 60
  done

  pkill chromium
  sleep 5
  pkill -9 chromium
  # Keep the log from growing forever.
  tail -n 500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
done
