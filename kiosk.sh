#!/bin/sh
# Starts Chromium fullscreen on the Pi's screen and restarts it:
#  - if the board stops checking in with the server (a safety net for hangs and
#    crashes on a 512MB Pi), and
#  - once when the screen wakes, if Chromium was started while it was asleep
#    (e.g. a reboot at night). Chromium can't go fullscreen on a display that's
#    off, so it would otherwise wake up as a normal window with tabs.
# Launched from ~/.config/labwc/autostart.
#
# Don't add --renderer-process-limit=1: with it Chromium never loads the board.

URL=http://localhost:8080
LOG=/home/pi/chromium-boot.log
STARTUP_GRACE=180  # seconds a fresh Chromium gets to load the board
STALE_AFTER=180    # seconds without a check-in before Chromium is restarted

# The desktop doesn't pass these to startup programs on this Pi.
export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/1000

status() { curl -s "$URL/api/kiosk"; }  # {"seconds_since_seen": N|null, "asleep": true|false}
is_asleep() { status | grep -q '"asleep": true'; }

until curl -s "$URL/api/kiosk" >/dev/null; do sleep 2; done
sleep 20  # let the rest of the boot settle

while true; do
  if is_asleep; then started_asleep=1; else started_asleep=0; fi
  echo "=== $(date) starting chromium$([ $started_asleep = 1 ] && echo ' (screen asleep)')" >> "$LOG"
  chromium --ozone-platform=wayland --no-memcheck --password-store=basic \
    --kiosk --incognito --no-first-run \
    --disable-extensions --disable-sync --disable-component-update \
    --disable-background-networking --disable-features=Translate,MediaRouter,OptimizationHints \
    --noerrdialogs --disable-infobars --check-for-update-interval=31536000 \
    --enable-logging=stderr "$URL" >> "$LOG" 2>&1 &

  sleep "$STARTUP_GRACE"
  while true; do
    s=$(status)
    age=$(echo "$s" | grep -o '"seconds_since_seen": [0-9]*' | grep -o '[0-9]*$')
    if [ -z "$age" ] || [ "$age" -gt "$STALE_AFTER" ]; then
      echo "=== $(date) board not checking in (last seen: ${age:-never}s ago), restarting chromium" >> "$LOG"
      break
    fi
    if [ $started_asleep = 1 ] && echo "$s" | grep -q '"asleep": false'; then
      echo "=== $(date) screen woke and chromium was started while asleep, restarting it fullscreen" >> "$LOG"
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
