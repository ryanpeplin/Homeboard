# Homeboard

A self-hosted DAKboard-style wall display: a 4-week calendar with daily forecasts, a clock, Fitbit steps, current weather, sunrise and moon phase, Spotify now-playing controls, and package deliveries found in your Gmail. It's built for a Raspberry Pi Zero 2 W driving a monitor, and it also works in any browser on your network.

- `server.py` is a small Python server. It fetches your calendars, weather, Fitbit, Spotify and shipping emails and serves the page.
- `static/` holds the page shown in the browser.
- `kiosk.sh` starts Chromium fullscreen on the Pi and restarts it if the board stops responding.
- `config.example.json` is the settings template. Your real settings go in `config.json`, and your Fitbit and Spotify logins in `tokens.json`, which is created automatically when you connect them. Packages found in your email are kept in `packages.json`, also created automatically.

> `config.json` and `tokens.json` contain your app passwords and private calendar links. They're listed in `.gitignore`, so they never go to GitHub. That also means a fresh copy of the repo doesn't have them, so keep a backup of both somewhere private.

## 1. Get the code and create `config.json`

Download the repo to your PC (it's private, so Git asks you to sign in to GitHub):

```bash
git clone https://github.com/ryanpeplin/Homeboard.git C:\Users\ryanp\Claude\homeboard
```

Then create your settings file from the template:

```bash
copy C:\Users\ryanp\Claude\homeboard\config.example.json C:\Users\ryanp\Claude\homeboard\config.json
```

If you have a backup of `config.json` and `tokens.json`, copy those into the folder instead, and you can skip step 3.

Then edit `config.json`:

| Section | What to set |
|---|---|
| `display.background` | Put an image in `static/backgrounds/` and point this at it. `background_dim` (0–1) darkens it so text stays readable. |
| `calendar.feeds` | One entry per calendar: `name`, a `color`, and its iCal URL (see below). `weeks` is how many rows to show. |
| `weather` | Your `lat`/`lon` (right-click a spot in Google Maps to copy them). `units` is `fahrenheit` or `celsius`. Weather comes from Open-Meteo, which needs no API key. |
| `fitbit` / `spotify` | Developer app credentials (see step 3). `fitbit.goal` is your daily step goal for the ring; `0` means 10,000. |
| `packages` | Your Gmail address and an app password, to show package deliveries (see [Package deliveries](#package-deliveries)). Leave them empty to hide the panel. |
| `sleep` | When the Pi's screen turns off overnight (see [Sleep schedule](#sleep-schedule)). |

**Where to find iCal URLs**
- **Google:** Calendar settings → pick the calendar → *Integrate calendar* → **Secret address in iCal format**. Google can take a few hours to update this feed.
- **iCloud:** Calendar app → share the calendar → **Public Calendar** → copy the `webcal://` link.
- **Outlook:** Settings → Calendar → Shared calendars → **Publish a calendar** → copy the ICS link.

## 2. Run it on your PC first

In PowerShell, from the homeboard folder (`cd C:\Users\ryanp\Claude\homeboard`):

```bash
python -m pip install -r requirements.txt
```

```bash
python server.py
```

Then open http://127.0.0.1:8080.

Only run one copy at a time. If you start a second copy while one is already running, it stops with "address already in use". Close the old one (Ctrl+C in its window) first.

## 3. Connect Fitbit and Spotify (one time)

Both services only accept the `127.0.0.1` redirect addresses below, so connect them on the PC. Your logins are saved in `tokens.json`, which gets copied to the Pi in step 4.

The server only reads `config.json` when it starts. Restart it after pasting in credentials.

**Fitbit (via the Google Health API):** the legacy Fitbit Web API was retired in September 2026, so Fitbit data now comes through a Google Cloud project.
1. Go to https://console.cloud.google.com and create a project.
2. Under **APIs & Services → Library**, enable **Google Health API**.
3. Under **OAuth consent screen** (Google Auth Platform), choose user type **External** and fill in the app name and your email.
   - Under **Data access**, add the scope `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`.
   - Under **Audience**, add the Google account your Fitbit is linked to as a test user.
4. Under **Clients → Create client**, choose **Web application** and add the redirect URI `http://127.0.0.1:8080/auth/fitbit/callback`.

Copy the Client ID and Client Secret into the `fitbit` section of `config.json`, restart the server, then open http://127.0.0.1:8080/auth/fitbit. Sign in with the Google account your Fitbit is linked to.

> While the app's publishing status is **Testing**, Google expires the login after 7 days and the step ring will stop updating. To avoid that, go to **Audience** and click **Publish app**. You'll then get an "unverified app" warning when you sign in. Since it's your own app, click **Advanced → Go to (app name)** and continue.

**Spotify:** go to https://developer.spotify.com/dashboard and create an app.
- APIs: **Web API**
- Redirect URI: `http://127.0.0.1:8080/auth/spotify/callback`, exactly as written. Using `localhost` or adding a trailing slash makes Spotify reject the sign-in.

Copy the Client ID and Client Secret into the `spotify` section of `config.json`, restart the server, then open http://127.0.0.1:8080/auth/spotify.

Play, pause, and skip need Spotify Premium. Showing what's playing works on any account. If you get an error about the user not being registered, add your Spotify email under **User Management** in the app's settings.

## 4. Set up the Raspberry Pi

Tested on a **Raspberry Pi Zero 2 W** running Raspberry Pi OS (trixie) with the labwc (Wayland) desktop.

### What you need
- The Pi, a microSD card, and a card reader for your PC.
- A **mini-HDMI to HDMI** adapter or cable. The Zero has a mini HDMI port.
- A 5V 2.5A micro-USB power supply, plugged into the port labeled **PWR** (the one at the end of the board).
- Your Wi-Fi name and password. The Zero 2 W only connects to **2.4 GHz** networks.

### 4.1 Write the SD card (on your PC)
1. Install **Raspberry Pi Imager** from https://www.raspberrypi.com/software/ and open it.
2. Make these choices:
   - **Device:** Raspberry Pi Zero 2 W
   - **OS:** the recommended **Raspberry Pi OS (with desktop)**. Don't pick a "Lite" version; those have no desktop, so they can't run Chromium.
   - **Storage:** your microSD card
3. When it asks to apply **OS customisation**, choose **Edit settings** and fill in:
   - **Hostname:** `homeboard`
   - **Username:** `pi`, plus a password. Everything below assumes the username is `pi`.
   - **Wireless LAN:** your Wi-Fi name, password, and country.
   - **Locale:** your time zone (`America/Chicago` here). The calendar and sleep schedule use it.
   - **Services tab:** turn on **Enable SSH** with password authentication.
4. Write the card.

### 4.2 First boot
Put the card in the Pi, connect the monitor, and plug in power. The first boot takes 3–5 minutes and may restart once.

If the Pi shows *"Drawing the desktop is using large amounts of memory. Consider disabling active desktop"*, you can ignore it. Step 4.6 turns the desktop off.

### 4.3 Connect from your PC
In PowerShell on your PC (type `yes` the first time, then your Pi password):
```bash
ssh pi@homeboard.local
```
If `homeboard.local` isn't found, find the Pi's IP address in your router's device list and use `ssh pi@<that-ip>`.

Update the system. This takes a while on a Zero:
```bash
sudo apt update && sudo apt full-upgrade -y
```

### 4.4 Copy the board to the Pi
Stop the server on your PC first, so only the Pi runs it. Then, in a **separate PowerShell window on your PC** (not the SSH window, because the Pi can't see your `C:` drive):
```bash
scp -r C:\Users\ryanp\Claude\homeboard pi@homeboard.local:~/
```
That copies your config, your Fitbit and Spotify logins (`tokens.json`), and the background image.

### 4.5 Install and start the server (in the SSH window)
```bash
cd ~/homeboard && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Create the service that runs the server at boot:
```bash
sudo nano /etc/systemd/system/homeboard.service
```
Paste this, then press Ctrl+O, Enter, and Ctrl+X to save and exit:
```ini
[Unit]
Description=Homeboard
After=network-online.target
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/homeboard
ExecStart=/home/pi/homeboard/.venv/bin/python server.py
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```
`PYTHONUNBUFFERED=1` makes the server's messages show up in its log right away.

Start it, and set it to start at every boot:
```bash
sudo systemctl enable --now homeboard
```
Check that it's running. You should see `active (running)`:
```bash
systemctl status homeboard --no-pager
```
You can now open `http://homeboard.local:8080` on your PC to check the board.

### 4.6 Show the board fullscreen at boot
Run the configuration tool:
```bash
sudo raspi-config
```
- **System Options → Boot / Auto Login → Desktop Autologin**, so the Pi logs into the desktop without a password prompt.
- **Display Options → Screen Blanking → No**, so the screen doesn't go blank on its own. The sleep schedule handles that.
- Choose **Finish**, and don't reboot yet.

Check which desktop and browser you have:
```bash
ps -e | grep -E 'labwc|wayfire|Xorg'
```
```bash
which chromium chromium-browser
```
The steps below assume `labwc` and `/usr/bin/chromium`. On older images the browser is `chromium-browser`; if so, change `chromium` to `chromium-browser` everywhere in `kiosk.sh`, including the `pkill` lines. For X11 (`Xorg`), see [Older X11 desktops](#older-x11-desktops).

Chromium is started by [`kiosk.sh`](kiosk.sh). Make it executable and set the desktop to run it at login:
```bash
chmod +x ~/homeboard/kiosk.sh && mkdir -p ~/.config/labwc && echo '/home/pi/homeboard/kiosk.sh &' > ~/.config/labwc/autostart
```
What `kiosk.sh` does:
- **Starts at the right time:** it waits for the server, plus 20 seconds for the rest of the boot to settle.
- **Restarts Chromium if it hangs.** The board checks in with the server every 30 seconds, and `kiosk.sh` asks the server how long ago that was. If the board hasn't loaded within 3 minutes of Chromium starting, or stops checking in for 3 minutes, Chromium is restarted. This is a safety net in case Chromium hangs or crashes on 512MB.
- **Restarts Chromium once at wake-up if it was started during sleep hours,** for example after a reboot or power cut at night. Chromium can't go fullscreen on a screen that's off, so without this it would wake up as a normal window with tabs and an address bar.
- **Logs to `~/chromium-boot.log`,** including a line each time it restarts Chromium and why.

The Chromium settings it uses:
- `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR` and `--ozone-platform=wayland` tell Chromium which screen to draw on.
- The `--disable-…` settings turn off Chromium features the board doesn't use, to save memory on 512MB.
- Don't add `--renderer-process-limit=1`. It looks like a memory saver, but with it Chromium never loads the board.
- `--no-memcheck` skips the *"It is not recommended to run Chromium on devices with less than 1GB of RAM"* pop-up.
- `--password-store=basic` skips the *"Choose password for new keyring"* pop-up.
- `--incognito` stops the "restore pages?" prompt after a power cut.

Turn off the desktop and taskbar. On 512MB they waste memory, and the taskbar draws on top of the board. This makes a backup first:
```bash
sudo cp /etc/xdg/labwc/autostart /etc/xdg/labwc/autostart.bak && sudo sed -i -e 's|^/usr/bin/lwrespawn /usr/bin/pcmanfm-pi &|# &|' -e 's|^/usr/bin/lwrespawn /usr/bin/wf-panel-pi &|# &|' /etc/xdg/labwc/autostart
```
A Raspberry Pi OS update may restore that file. If the desktop or taskbar comes back, run the command again. To undo it:
```bash
sudo cp /etc/xdg/labwc/autostart.bak /etc/xdg/labwc/autostart
```

Reboot:
```bash
sudo reboot
```
Within about 2 minutes the board should be on screen, fullscreen, with no mouse pointer. The page hides the pointer on the Pi's own screen. To check that it's running, use `curl -s localhost:8080/api/kiosk` over SSH: a number under about 30 means the board is checking in.

### 4.7 Set up the screen on/off commands
Install `wlopm`, which puts the monitor into standby and wakes it:
```bash
sudo apt install -y wlopm
```
Get your monitor's output name:
```bash
WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 wlr-randr | grep -E '^[^ ]|Enabled'
```
Look for the `HDMI-…` line, for example `HDMI-A-1 "HannStar …"`. Test it. The monitor should go to standby and come back after 10 seconds:
```bash
WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 wlopm --off HDMI-A-1; sleep 10; WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 wlopm --on HDMI-A-1
```
Put that name into the `sleep` commands in `config.json` (see [Sleep schedule](#sleep-schedule)), copy the config to the Pi, and restart the server (see [Updating the Pi later](#updating-the-pi-later)).

> Don't use `wlr-randr --output … --off` for this. It disconnects the output completely, and on this Pi `wlr-randr --on` then fails with "failed to apply configuration", so the screen never comes back.

## Sleep schedule

The Pi's screen can turn off overnight. This is the `sleep` section of `config.json` as used on the Pi Zero 2 W:

```json
"sleep": {
  "enabled": true,
  "awake": {
    "default": ["07:00", "22:00"],
    "sat": ["08:00", "23:30"],
    "sun": ["08:00", "23:00"]
  },
  "off_command": "WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 wlopm --off HDMI-A-1",
  "on_command": "WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 wlopm --on HDMI-A-1"
}
```

**The schedule:**
- `awake` lists the times the screen is **on**, using 24-hour times. `default` covers any day you don't list (`mon` … `sun`).
- A window can run past midnight, for example `["08:00", "01:00"]`. In that case, 00:00–01:00 counts toward that same weekday.

**What happens during sleep hours:**
- **The Pi's screen:** the page goes black and stops checking Spotify and steps. When it wakes, everything refreshes immediately.
- **Other devices:** the board stays visible at all hours. Only the Pi's own screen (the page opened as `localhost`) follows the schedule.
- **The monitor:** `off_command` turns off the HDMI signal, so the monitor shows "no signal" or goes into standby. `on_command` turns it back on in the morning. Leave both empty to just black out the page.

**Normal behavior that looks odd:**
- At boot the server starts before the desktop does, so its first attempts to switch the screen fail ("failed to connect to display"). It retries every 30 seconds until they work.
- While asleep, the server re-sends the off command every 30 seconds, in case something else wakes the screen.
- `wlopm` only puts the monitor to sleep, so `wlr-randr` still shows HDMI as `Enabled: yes` overnight. That's expected.

**If the board is on a TV:** you can switch the TV itself into standby and back over HDMI-CEC. Install `cec-utils`, then use `echo 'standby 0' | cec-client -s -d 1` to turn it off and `echo 'on 0' | cec-client -s -d 1` to turn it on.

## Package deliveries

The **Deliveries** panel in the sidebar lists packages on the way. The server finds them by reading shipping emails in your Gmail. It doesn't contact the carriers, so each status comes from the subject line of the newest email about that package.

### Set it up
1. Your Google account needs **2-Step Verification** turned on (Google Account → **Security**).
2. Go to https://myaccount.google.com/apppasswords, create an app password named `Homeboard`, and copy the 16-letter password.
3. If your Gmail settings have an IMAP setting (**See all settings → Forwarding and POP/IMAP**), make sure IMAP is enabled.
4. Fill in the `packages` section of `config.json`, then restart the server:
   ```json
   "packages": {
     "email": "you@gmail.com",
     "app_password": "abcd efgh ijkl mnop",
     "days": 14,
     "keep_delivered_days": 2,
     "refresh_minutes": 15
   }
   ```
   - `days`: how far back to look for shipping emails. A package is also dropped if it hasn't had an email in that long.
   - `keep_delivered_days`: how long a delivered package stays on the board.
   - `refresh_minutes`: how often Gmail is checked.

> An app password gives full access to your mailbox. It's only stored in `config.json`, which never goes to GitHub. The server only reads mail, and never marks anything as read. To revoke access, delete the app password at the link above.

### What it finds
- **UPS** (`1Z…`), **USPS** (20–22 digits starting with 9x), **FedEx** (12 or 15 digits) and **Amazon Logistics** (`TBA…`) tracking numbers, in the email text or inside "Track package" links.
  - USPS and FedEx numbers are just digits, so they only count when they come right after a label like "Tracking number:" or appear in a tracking link. That keeps order and phone numbers out.
- **Amazon orders:** Amazon's own emails rarely include a tracking number, so the panel follows the order number instead. It shows the item name from Amazon's emails (e.g. *Zevo Flying Insect Trap +1*).
  - **Orders that haven't shipped yet:** an *Ordered:* email adds the order as *Ordered, due Fri*, dimmed, using the latest "Arriving …" date in the email. When it ships, the same row turns into *Shipped*. An order Amazon sends in several shipments stays one row.
  - Only Amazon orders show before they ship. Other stores' order confirmations use a different order number (or come from a different address) than their shipping emails, so the board couldn't connect the two.
  - One Amazon package can contain items from several orders, and Amazon's emails don't always list the same order number first. An email is matched to a package if it shares any order number with it.
  - A later email for an order that was already delivered means another shipment, so the package shows as on the way again, with that shipment's item and date.
  - *Delivery estimate update* emails count as *Delayed* when they say the package is delayed, and the board shows the new date, e.g. *Delayed to Wed*. When the subject doesn't name the item, the name comes from the email's item list.
- **Status:** *Ordered* (Amazon only), *Shipped*, *Out for delivery*, *Delayed* or *Delivered*, from the newest email's subject. Subjects like "Your package is here" or "has arrived" also count as delivered. Once a package is delivered it stays delivered.
- **When no delivered email comes:** some stores never send one, and Amazon sometimes doesn't. A package still *Out for delivery* a day later counts as delivered. A shipped or ordered package is dropped once its expected date is more than `keep_delivered_days` past.
- **Expected delivery date:** read from wording like "Expected delivery on Tuesday, October 20", "Scheduled Delivery: 10/20/2026", "Arriving tomorrow" or "Estimated delivery: Oct 20 – 23". A shipped package then shows *Arrives today*, *Arrives tomorrow*, *Arrives Tue*, or a date like *Arrives Oct 28* when it's more than a week out.
  - Dates without a year, weekdays and "tomorrow" count from the day the email was sent. For a range, the later date is used.
  - A newer email with a different date replaces the old one.
  - If no date is found, or the date passes without a newer email, the package just shows *Shipped*.
  - Emails that list several packages (like USPS Informed Delivery) don't set a date, since there's no telling which date belongs to which package.
- **Name:** the store the email came from, such as "Target". If the first email came from the carrier, a later email from the store replaces it.

### On the board
- The list is sorted *Out for delivery*, *Delayed*, *Shipped*, *Ordered*, then *Delivered*, and within each by expected date, soonest first. Up to 10 packages show, then "+N more".
- On other devices, clicking a package opens its tracking page. The Pi's own screen shows no links, so a tap can't take the kiosk away from the board.
- The panel is hidden when nothing is on the way. If Gmail can't be read, the panel shows "Not updating" and the reason.
- The first check reads up to 300 shipping emails from the last `days` days and can take a minute or two on the Pi. Later checks only read new emails.
- Packages whose emails have no tracking number, or a format not listed above, won't show up.

## Updating the Pi later

Edit files on your PC, then copy the changed file to the Pi from a PowerShell window on the PC. For example, for `config.json`:
```bash
scp C:\Users\ryanp\Claude\homeboard\config.json pi@homeboard.local:~/homeboard/config.json
```
Use the same pattern for `server.py` and `kiosk.sh`, or for files in `static/` (copy those to `~/homeboard/static/`).

What to do after copying:
- **`config.json` or `server.py`:** restart the server, over SSH:
  ```bash
  sudo systemctl restart homeboard
  ```
- **`kiosk.sh`:** make sure it's still executable, then reboot:
  ```bash
  chmod +x ~/homeboard/kiosk.sh && sudo reboot
  ```
- **Files in `static/`:** nothing. The page picks them up the next time it loads, at the next reboot or the next wake-up.

Don't overwrite the Pi's `tokens.json` with an old copy from your PC. The Pi keeps its logins up to date in its own copy.

To save changes to GitHub, commit and push from the homeboard folder on your PC (`git add -A`, `git commit -m "…"`, `git push`). `config.json` and `tokens.json` are left out automatically.

## Troubleshooting

| Symptom | Check |
|---|---|
| Board is black on the Pi | Probably the sleep schedule. Check whether it's outside your `awake` hours. |
| Screen doesn't switch on or off on schedule | Run `journalctl -u homeboard -b --no-pager \| grep sleep \| tail -20`. Repeated `exited 1` lines show the error from the on/off command. |
| Screen black with a mouse pointer during awake hours | Chromium hasn't loaded the board. Wait about 4 minutes, because `kiosk.sh` restarts Chromium by then. If it stays black, check `tail -40 ~/chromium-boot.log` and `curl -s localhost:8080/api/kiosk`, and make sure `~/.config/labwc/autostart` contains `/home/pi/homeboard/kiosk.sh &`. |
| Board shows as a normal window, with tabs and an address bar | Chromium was started while the screen was off. `kiosk.sh` restarts it within a minute of the screen waking. If it doesn't, check `grep '===' ~/chromium-boot.log \| tail` and make sure the Pi has the latest `kiosk.sh` and `server.py`. A reboot during awake hours also fixes it. |
| Board very slow | Usually memory. Keep the background at the screen's resolution, and keep the Chromium settings from step 4.6. |
| Server problems | Status: `systemctl status homeboard --no-pager`. Log: `journalctl -u homeboard -n 50 --no-pager`. |
| Deliveries panel says "Not updating" | The message gives the reason. "Gmail sign-in failed" usually means the app password was revoked or mistyped. Make a new one and restart the server. |
| A package is missing from Deliveries | Its emails may not include a tracking number, or use a format the board doesn't know (see [What it finds](#what-it-finds)). |
| Spotify panel says "Spotify not working" | The message under it gives the reason. Usually the login needs redoing on the PC; then copy `tokens.json` to the Pi. |
| Desktop, taskbar or a Chromium pop-up came back after an update | Run the matching command from step 4.6 again. |
| Board doesn't load on the PC | Make sure exactly one copy of the server is running (see step 2). |

## Older X11 desktops

Untested. If `ps -e | grep -E 'labwc|wayfire|Xorg'` shows `Xorg` instead of `labwc`:
- **Startup:** add this line to `~/.config/lxsession/LXDE-pi/autostart`:
  ```
  @chromium --no-memcheck --password-store=basic --kiosk --incognito --noerrdialogs --disable-infobars --check-for-update-interval=31536000 http://localhost:8080
  ```
- **Screen on/off:** use these sleep commands:
  ```json
  "off_command": "DISPLAY=:0 xset dpms force off",
  "on_command": "DISPLAY=:0 xset dpms force on && DISPLAY=:0 xset s off -dpms"
  ```

## Future updates

### Match Google Calendar event colors
**Goal:** show each event in the color picked for it in Google Calendar (red for work, yellow for personal, and so on), instead of one color per feed.

**Why it needs the API:** Google's secret iCal links (*Secret address in iCal format*) leave out per-event colors. A check on 2026-10-09 found no color information in any of the feeds (2,431 events in the main calendar).

**Plan:**
- **Google Cloud:** in the same project used for Fitbit, enable the **Google Calendar API** and add the read-only scope `https://www.googleapis.com/auth/calendar.readonly`.
- **Server, sign-in:** request that scope alongside the Fitbit one, so a single Google sign-in at `/auth/fitbit` covers both. Requesting the new scope means signing in again once.
- **Server, fetching:** for Google calendars, use the Calendar API instead of the iCal URL. That's `events.list` with `singleEvents=true` (which expands recurring events) and `timeMin`/`timeMax` set to the board's date range.
- **Colors:** each event's `colorId` maps to a hex color via the `colors.get` endpoint. Events without a `colorId` use the calendar's own color from `calendarList`.
- **Other calendars:** non-Google calendars keep using iCal URLs. In `config.json`, a feed could be marked e.g. `"google_calendar_id": "primary"` in place of `url`.
- **Page:** no changes needed. It already colors each event from the server's `color` field.

## Notes
- **Pi Zero 2 W (512MB RAM):** use a JPEG background at your screen's resolution (1366×768 for the HannStar HF199H), not a large photo. The original 4.8MB, 2560×1440 background made the board very slow; the current `background-1366.jpg` is 254KB. The page only redraws when data changes. If Chromium is ever sluggish, raise the Spotify polling interval (10 s) on the last lines of `static/app.js`.
- **Update times:** the clock updates every second, Spotify every 10 seconds, the calendar every 10 minutes, steps about every 5 minutes, and weather and package deliveries every 15 minutes.
- **Your network:** any device on your network can open the board, including the Spotify play/pause buttons. Only run it on a trusted home network.
- **Calendar errors:** if a feed fails to load, the rest of the board still loads. The failure is logged in the browser console.
