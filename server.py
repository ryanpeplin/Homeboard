"""Homeboard: a small self-hosted DAKboard-style wall display server.

Serves static/ and a JSON API that proxies calendars (iCal), weather (Open-Meteo),
Fitbit steps (via the Google Health API) and Spotify now-playing. Run:  python server.py
"""
import json
import mimetypes
import secrets
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import certifi
import icalendar
import recurring_ical_events

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))  # -sig: tolerate Notepad's BOM
TOKENS_FILE = ROOT / "tokens.json"
PORT = CONFIG.get("port", 8080)
REDIRECT = "http://127.0.0.1:{port}/auth/{svc}/callback"
SSL = ssl.create_default_context(cafile=certifi.where())  # OS cert stores can carry stale roots

_lock = threading.Lock()
_refresh_lock = threading.Lock()
_cache = {}
_oauth_states = {}


# ---------- helpers ----------

def http(url, method="GET", headers=None, data=None, form=None, body=None):
    """Return (status, parsed JSON or text or None)."""
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers = {**(headers or {}), "Content-Type": "application/x-www-form-urlencoded"}
    if body is not None:
        data = json.dumps(body).encode()
        headers = {**(headers or {}), "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": "homeboard", **(headers or {})})
    if method in ("PUT", "POST") and data is None:
        req.data = b""
    try:
        with urllib.request.urlopen(req, timeout=20, context=SSL) as r:
            body = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        body, status = e.read(), e.code
    if not body:
        return status, None
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body.decode("utf-8", "replace")


def cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = fn()
    _cache[key] = (time.time(), value)
    return value


def load_tokens():
    if TOKENS_FILE.exists():
        return json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    return {}


def save_token(svc, tok):
    with _lock:
        tokens = load_tokens()
        tokens[svc] = tok
        TOKENS_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")


# ---------- calendar ----------

def to_local(v):
    """Return (datetime, all_day) for an icalendar date/datetime."""
    if isinstance(v, datetime):
        return v.astimezone(), False  # naive (floating) times are taken as local
    return datetime(v.year, v.month, v.day).astimezone(), True


def fetch_calendar():
    cfg = CONFIG["calendar"]
    today = date.today()
    start_of_week = 6 if cfg.get("week_start", "sunday") == "sunday" else 0
    first = today - timedelta(days=(today.weekday() - start_of_week) % 7)
    last = first + timedelta(days=7 * cfg.get("weeks", 4))
    events, errors = [], []
    for feed in cfg["feeds"]:
        url = feed["url"].replace("webcal://", "https://", 1)
        try:
            status, text = http(url)
            if status != 200 or not isinstance(text, str):
                raise RuntimeError(f"HTTP {status}")
            cal = icalendar.Calendar.from_ical(text)
            for ev in recurring_ical_events.of(cal).between(first, last):
                start, all_day = to_local(ev["DTSTART"].dt)
                if "DTEND" in ev:
                    end, _ = to_local(ev["DTEND"].dt)
                elif "DURATION" in ev:
                    end = start + ev["DURATION"].dt
                else:
                    end = start + (timedelta(days=1) if all_day else timedelta(0))
                events.append({
                    "title": str(ev.get("SUMMARY", "(no title)")),
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "allDay": all_day,
                    "color": feed.get("color", "#d50000"),
                })
        except Exception as e:  # one bad feed shouldn't blank the board
            errors.append(f"{feed.get('name', url)}: {e}")
    events.sort(key=lambda e: (e["start"], e["title"]))
    return {"first": first.isoformat(), "weeks": cfg.get("weeks", 4), "events": events, "errors": errors}


# ---------- weather ----------

def fetch_weather():
    loc = CONFIG["weather"]
    q = urllib.parse.urlencode({
        "latitude": loc["lat"], "longitude": loc["lon"],
        "current": "temperature_2m,apparent_temperature,weather_code,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset",
        "temperature_unit": loc.get("units", "fahrenheit"),
        "timezone": "auto", "forecast_days": 16,
    })
    status, data = http("https://api.open-meteo.com/v1/forecast?" + q)
    if status != 200:
        raise RuntimeError(f"Open-Meteo HTTP {status}: {data}")
    return data


# ---------- OAuth (Fitbit + Spotify) ----------

OAUTH = {
    # Fitbit data now comes through the Google Health API (the legacy Fitbit Web API
    # was retired in September 2026), so this is a Google OAuth client.
    "fitbit": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
        "extra": {"access_type": "offline", "prompt": "consent"},  # always return a refresh token
    },
    "spotify": {
        "authorize": "https://accounts.spotify.com/authorize",
        "token": "https://accounts.spotify.com/api/token",
        "scope": "user-read-currently-playing user-read-playback-state user-modify-playback-state",
    },
}


def token_request(svc, form):
    creds = {"client_id": CONFIG[svc]["client_id"], "client_secret": CONFIG[svc]["client_secret"]}
    status, data = http(OAUTH[svc]["token"], "POST", form={**form, **creds})
    if status != 200:
        raise RuntimeError(f"{svc} token HTTP {status}: {data}")
    old = load_tokens().get(svc, {})
    tok = {
        "access_token": data["access_token"],
        # Refreshes usually omit refresh_token; keep the one we have.
        "refresh_token": data.get("refresh_token", old.get("refresh_token")),
        "expires_at": time.time() + data.get("expires_in", 3600) - 60,
    }
    save_token(svc, tok)
    return tok


def access_token(svc):
    with _lock:
        tok = load_tokens().get(svc)
    if not tok:
        return None
    if time.time() >= tok["expires_at"]:
        with _refresh_lock:  # serialize refreshes so concurrent requests don't each refresh
            tok = load_tokens().get(svc)
            if time.time() >= tok["expires_at"]:
                tok = token_request(svc, {"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    return tok["access_token"]


def api(svc, url, method="GET", body=None):
    tok = access_token(svc)
    if not tok:
        return 401, {"error": f"not connected - open http://127.0.0.1:{PORT}/auth/{svc} on the server machine"}
    return http(url, method, headers={"Authorization": f"Bearer {tok}"}, body=body)


def civil(d):
    return {"date": {"year": d.year, "month": d.month, "day": d.day}, "time": {"hours": 0}}


def fetch_fitbit():
    today = date.today()
    status, data = api(
        "fitbit", "https://health.googleapis.com/v4/users/me/dataTypes/steps/dataPoints:dailyRollUp", "POST",
        body={"range": {"start": civil(today), "end": civil(today + timedelta(days=1))}, "windowSizeDays": 1},
    )
    if status != 200:
        return {"error": data}
    points = data.get("rollupDataPoints") or []
    steps = int(points[0].get("steps", {}).get("countSum", 0)) if points else 0  # int64 may arrive as a string
    return {"steps": steps, "goal": CONFIG["fitbit"].get("goal") or 10000}


def fetch_spotify():
    status, data = api("spotify", "https://api.spotify.com/v1/me/player/currently-playing")
    if status == 204 or data is None:
        return {"playing": False, "item": None}
    if status != 200:
        return {"error": data}
    item = data.get("item")  # None during ads and for some local files
    if not item:
        return {"playing": data.get("is_playing", False), "item": None}
    images = (item.get("album") or {}).get("images") or [{}]
    return {
        "playing": data.get("is_playing", False),
        "item": {
            "title": item.get("name"),
            "artist": ", ".join(a["name"] for a in item.get("artists", [])) or (item.get("show") or {}).get("name"),
            "art": images[-1].get("url") if len(images) < 2 else images[1].get("url"),  # ~300px when available
        },
    }


SPOTIFY_ACTIONS = {
    "play": ("PUT", "play"), "pause": ("PUT", "pause"),
    "next": ("POST", "next"), "previous": ("POST", "previous"),
}


# ---------- sleep schedule ----------

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_asleep = False
_kiosk_seen = None  # last time the wall display's page polled /api/sleep


def is_asleep(now=None):
    """True outside today's awake window. A window like ["07:00", "01:00"] runs past midnight."""
    cfg = CONFIG.get("sleep") or {}
    if not cfg.get("enabled"):
        return False
    now = now or datetime.now()
    awake = cfg.get("awake", {})
    window = awake.get(WEEKDAYS[now.weekday()]) or awake.get("default")
    if not window:
        return False
    t, on, off = now.strftime("%H:%M"), window[0], window[1]
    is_awake = on <= t < off if on <= off else (t >= on or t < off)
    return not is_awake


def run_display_cmd(key):
    """Run the configured command; True if it succeeded (or there's nothing to run)."""
    cmd = (CONFIG.get("sleep") or {}).get(key)
    if not cmd:
        return True
    try:
        result = subprocess.run(cmd, shell=True, timeout=20, capture_output=True, text=True)
    except Exception as e:
        print(f"sleep: {key} failed: {e}", flush=True)
        return False
    if result.returncode != 0:
        print(f"sleep: {key} exited {result.returncode}: {result.stderr.strip()}", flush=True)
    return result.returncode == 0


def sleep_loop():
    """Check the schedule every 30 s and run the off/on command when the state flips.

    A failed command is retried on the next check. At boot the server starts before
    the desktop session exists, so the first attempts are expected to fail.

    While asleep the off command is re-sent on every check, in case something else
    wakes the display. The on command only runs on the transition.
    """
    global _asleep
    applied = None  # the state the display was last successfully put into
    while True:
        _asleep = is_asleep()
        if _asleep != applied or _asleep:
            if run_display_cmd("off_command" if _asleep else "on_command"):
                if _asleep != applied:
                    print(f"sleep: display {'off' if _asleep else 'on'}", flush=True)
                applied = _asleep
        time.sleep(30)


# ---------- HTTP handler ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # self.path is unset when a request fails before it's parsed (e.g. a dropped connection).
        if not getattr(self, "path", "").startswith(("/api/spotify", "/api/sleep")):  # polled often; keep the log readable
            super().log_message(fmt, *args)

    def send(self, status, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, url):
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def do_GET(self):
        global _kiosk_seen
        path, _, query = self.path.partition("?")
        params = dict(urllib.parse.parse_qsl(query))
        try:
            if path == "/api/sleep":
                if self.client_address[0] == "127.0.0.1":  # only the wall display's own page polls this locally
                    _kiosk_seen = time.time()
                return self.send(200, {"asleep": is_asleep()})
            if path == "/api/kiosk":
                # kiosk.sh restarts Chromium when the page stops checking in, and once
                # on wake if it was started while the display was off.
                age = None if _kiosk_seen is None else int(time.time() - _kiosk_seen)
                return self.send(200, {"seconds_since_seen": age, "asleep": is_asleep()})
            if path == "/api/config":
                return self.send(200, CONFIG.get("display", {}))
            if path == "/api/calendar":
                return self.send(200, cached("cal", CONFIG["calendar"].get("refresh_minutes", 10) * 60, fetch_calendar))
            if path == "/api/weather":
                return self.send(200, cached("wx", 15 * 60, fetch_weather))
            if path == "/api/fitbit":
                return self.send(200, cached("fitbit", 5 * 60, fetch_fitbit))
            if path == "/api/spotify":
                return self.send(200, fetch_spotify())
            if path.startswith("/auth/"):
                return self.auth(path.split("/")[2], path.endswith("/callback"), params)
            return self.static(path)
        except Exception as e:
            return self.send(500, {"error": str(e)})

    def do_POST(self):
        parts = self.path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "spotify"] and parts[2] in SPOTIFY_ACTIONS:
            method, ep = SPOTIFY_ACTIONS[parts[2]]
            status, data = api("spotify", f"https://api.spotify.com/v1/me/player/{ep}", method)
            return self.send(200 if status < 300 else status, data or {"ok": True})
        self.send(404, {"error": "not found"})

    def auth(self, svc, callback, params):
        if svc not in OAUTH:
            return self.send(404, {"error": "unknown service"})
        redirect_uri = REDIRECT.format(port=PORT, svc=svc)
        if not callback:
            state = secrets.token_urlsafe(16)
            _oauth_states[state] = svc
            return self.redirect(OAUTH[svc]["authorize"] + "?" + urllib.parse.urlencode({
                "response_type": "code", "client_id": CONFIG[svc]["client_id"],
                "redirect_uri": redirect_uri, "scope": OAUTH[svc]["scope"], "state": state,
                **OAUTH[svc].get("extra", {}),
            }))
        if _oauth_states.pop(params.get("state"), None) != svc or "code" not in params:
            return self.send(400, {"error": "bad state or missing code", "params": params})
        token_request(svc, {"grant_type": "authorization_code", "code": params["code"], "redirect_uri": redirect_uri})
        _cache.pop(svc, None)
        self.send(200, f"<h2>{svc} connected.</h2><a href='/'>Back to the board</a>".encode(), "text/html")

    def static(self, path):
        rel = "index.html" if path == "/" else urllib.parse.unquote(path.lstrip("/"))
        file = (STATIC / rel).resolve()
        if STATIC.resolve() not in file.parents or not file.is_file():
            return self.send(404, {"error": "not found"})
        self.send(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")


class Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second copy bind the same port silently, leaving
    # an old instance answering requests. Fail loudly there instead.
    allow_reuse_address = sys.platform != "win32"


if __name__ == "__main__":
    print(f"Homeboard on http://127.0.0.1:{PORT}  (and on this machine's LAN IP)")
    threading.Thread(target=sleep_loop, daemon=True).start()
    Server(("0.0.0.0", PORT), Handler).serve_forever()
