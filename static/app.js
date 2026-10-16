// Homeboard front end. Kept deliberately light for a 512MB Raspberry Pi Zero 2 W:
// DOM is rebuilt only when fetched data actually changes.

const DOW = ["S", "M", "T", "W", "T", "F", "S"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAY = 86400000;
const RING = 2 * Math.PI * 52;

let cfg = { clock_24h: true };
let cal = null, wx = null;
const last = {};  // last JSON seen per endpoint, to skip no-op re-renders

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};
const pad = (n) => String(n).padStart(2, "0");
const dateKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const fmtTime = (d) => cfg.clock_24h
  ? `${pad(d.getHours())}:${pad(d.getMinutes())}`
  : `${d.getHours() % 12 || 12}:${pad(d.getMinutes())}${d.getHours() < 12 ? "a" : "p"}`;

async function getJSON(name, url) {
  const r = await fetch(url);
  const text = await r.text();
  if (!r.ok) throw new Error(`${url}: ${text}`);
  const changed = last[name] !== text;
  last[name] = text;
  return { data: JSON.parse(text), changed };
}

// ---------- clock ----------

let shownMinute = "", shownDay = "";
function tick() {
  const now = new Date();
  const minute = fmtTime(now).replace(/[ap]$/, "");
  if (minute !== shownMinute) {
    shownMinute = minute;
    $("clock").textContent = minute;
  }
  const day = dateKey(now);
  if (day !== shownDay) {
    const first = shownDay === "";
    shownDay = day;
    $("date").textContent = now.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
    $("moon").textContent = moonPhase(now);
    if (!first) { loadCalendar(true); loadWeather(true); }
  }
}

function moonPhase(d) {
  const synodic = 29.530588853;
  const age = (((d - Date.UTC(2000, 0, 6, 18, 14)) / DAY) % synodic + synodic) % synodic;
  const names = ["New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
                 "Full moon", "Waning gibbous", "Last quarter", "Waning crescent"];
  return names[Math.floor((age / synodic) * 8 + 0.5) % 8];
}

// ---------- weather ----------

function wxIcon(code, day = true) {
  const dn = day ? "day" : "night";
  if (code === 0) return day ? "wi-day-sunny" : "wi-night-clear";
  if (code <= 2) return day ? "wi-day-cloudy" : "wi-night-alt-cloudy";
  if (code === 3) return "wi-cloudy";
  if (code <= 48) return "wi-fog";
  if (code <= 57) return "wi-sprinkle";
  if (code <= 67) return "wi-rain";
  if (code <= 77) return "wi-snow";
  if (code <= 82) return `wi-${dn}-showers`;
  if (code <= 86) return "wi-snow";
  return "wi-thunderstorm";
}

async function loadWeather(force) {
  try {
    const { data, changed } = await getJSON("wx", "/api/weather");
    if (!changed && !force) return;
    wx = data;
    const c = wx.current;
    $("now-temp").textContent = `${Math.round(c.temperature_2m)}°`;
    $("now-icon").className = `wi ${wxIcon(c.weather_code, c.is_day)}`;
    $("feels").textContent = `Feels like ${Math.round(c.apparent_temperature)}`;
    const today = wx.daily.time.indexOf(dateKey(new Date()));
    if (today >= 0) {
      const [h, m] = wx.daily.sunrise[today].slice(11, 16).split(":").map(Number);
      $("sunrise").textContent = fmtTime(new Date(2000, 0, 1, h, m));
    }
    renderCalendar();
  } catch (e) { console.warn(e); }
}

// ---------- calendar ----------

async function loadCalendar(force) {
  try {
    const { data, changed } = await getJSON("cal", "/api/calendar");
    if (data.errors.length) console.warn("calendar feed errors:", data.errors);
    if (!changed && !force) return;
    cal = data;
    renderCalendar();
  } catch (e) { console.warn(e); }
}

function renderCalendar() {
  if (!cal) return;
  const [y, m, d] = cal.first.split("-").map(Number);
  const first = new Date(y, m - 1, d);
  const todayKey = dateKey(new Date());
  const events = cal.events.map((e) => ({ ...e, s: new Date(e.start), e: new Date(e.end) }));
  const forecast = {};
  if (wx) wx.daily.time.forEach((t, i) => forecast[t] = i);

  $("dow").replaceChildren(...[...Array(7)].map((_, i) => el("div", null, DOW[(first.getDay() + i) % 7])));

  const cells = [];
  for (let i = 0; i < cal.weeks * 7; i++) {
    const day = new Date(first.getFullYear(), first.getMonth(), first.getDate() + i);
    const next = new Date(day.getFullYear(), day.getMonth(), day.getDate() + 1);
    const key = dateKey(day);
    const cell = el("div", "day" + (key < todayKey ? " past" : key === todayKey ? " today" : ""));

    const labelMonth = (i === 0 || day.getDate() === 1) && key !== todayKey;
    const num = el("div", "num" + (labelMonth ? " month" : ""));
    num.append(el("span", null, labelMonth ? MONTHS[day.getMonth()] : day.getDate()));
    cell.append(num);

    const w = el("div", "wx");
    const fi = forecast[key];
    if (fi != null && key >= todayKey) {
      w.append(el("i", `wi ${wxIcon(wx.daily.weather_code[fi])}`),
        `${Math.round(wx.daily.temperature_2m_max[fi])}° ${Math.round(wx.daily.temperature_2m_min[fi])}°`);
    }
    cell.append(w);

    const list = el("div", "events");
    const bars = [], timed = [];
    for (const ev of events) {
      const isBar = ev.allDay || ev.e - ev.s >= DAY;
      if (isBar ? (ev.s < next && ev.e > day) : (ev.s >= day && ev.s < next)) (isBar ? bars : timed).push(ev);
    }
    for (const ev of bars) {
      const b = el("div", "bar" + (ev.s < day ? " cont" : ""), ev.title);
      b.style.background = ev.color;
      list.append(b);
    }
    for (const ev of timed) {
      const t = el("div", "timed");
      const dot = el("span", "dot");
      dot.style.background = ev.color;
      t.append(dot, el("span", "time", fmtTime(ev.s)), ev.title);
      list.append(t);
    }
    cell.append(list);
    cells.push(cell);
  }
  $("grid").replaceChildren(...cells);
}

// ---------- fitbit ----------

async function loadFitbit() {
  try {
    const { data, changed } = await getJSON("fitbit", "/api/fitbit");
    if (!changed || data.error) return data.error && console.warn("fitbit:", data.error);
    $("steps-count").textContent = data.steps.toLocaleString();
    $("steps-arc").style.strokeDashoffset = RING * (1 - Math.min(data.steps / data.goal, 1));
  } catch (e) { console.warn(e); }
}

// ---------- spotify ----------

let playing = false;
async function loadSpotify() {
  try {
    const { data, changed } = await getJSON("spotify", "/api/spotify");
    if (!changed) return;
    $("spotify").classList.remove("hidden");
    if (data.error) {
      // Show why instead of hiding the card, so a missing connection is obvious.
      const msg = data.error.error?.message || data.error.error || data.error;
      $("sp-track").style.visibility = "visible";
      $("sp-title").textContent = "Spotify not working";
      $("sp-artist").textContent = typeof msg === "string" ? msg : JSON.stringify(msg);
      $("sp-art").removeAttribute("src");
      return console.warn("spotify:", data.error);
    }
    playing = data.playing;
    $("sp-toggle").firstElementChild.className = `fa-solid fa-${playing ? "pause" : "play"}`;
    const it = data.item;
    $("sp-track").style.visibility = it ? "visible" : "hidden";
    if (it) {
      $("sp-title").textContent = it.title || "";
      $("sp-artist").textContent = it.artist || "";
      if ($("sp-art").getAttribute("src") !== (it.art || "")) $("sp-art").setAttribute("src", it.art || "");
    }
  } catch (e) { console.warn(e); }
}

async function spotify(action) {
  await fetch(`/api/spotify/${action}`, { method: "POST" }).catch(console.warn);
  setTimeout(loadSpotify, 700);
}

document.querySelectorAll("#sp-controls [data-act]").forEach((b) => b.onclick = () => spotify(b.dataset.act));
$("sp-toggle").onclick = () => spotify(playing ? "pause" : "play");

// ---------- packages ----------

const PK_ICON = { "Out for delivery": "fa-truck-fast", "Delayed": "fa-triangle-exclamation", "Delivered": "fa-circle-check" };
const PK_MAX = 4;  // rows that fit in the sidebar
async function loadPackages() {
  try {
    const { data, changed } = await getJSON("packages", "/api/packages");
    if (data.error) console.warn("packages:", data.error);
    if (!changed) return;
    const list = data.packages;
    $("packages").hidden = !list.length && !data.error;
    const rows = list.slice(0, PK_MAX).map((p) => {
      // Links only off the wall display, where a tap would navigate the kiosk away from the board.
      const row = el(IS_KIOSK ? "div" : "a", "pk" + (p.status === "Out for delivery" ? " out" : ""));
      if (!IS_KIOSK) { row.href = p.link; row.target = "_blank"; row.rel = "noopener"; }
      const day = p.status === "Delivered"
        ? " " + new Date(p.status_at * 1000).toLocaleDateString(undefined, { weekday: "short" }) : "";
      row.append(el("i", `fa-solid ${PK_ICON[p.status] || "fa-box"}`), el("span", "pk-label", p.label),
        el("span", "pk-status", p.status + day));
      return row;
    });
    if (list.length > PK_MAX) rows.push(el("div", "pk-more", `+${list.length - PK_MAX} more`));
    if (data.error) rows.push(el("div", "pk-more", `Not updating: ${data.error}`));
    $("pk-list").replaceChildren(...rows);
  } catch (e) { console.warn(e); }
}

// ---------- sleep ----------

// Only the wall display itself (its kiosk opens http://localhost:8080) follows the
// schedule; the board stays visible when opened from another device.
const IS_KIOSK = ["localhost", "127.0.0.1"].includes(location.hostname);
if (IS_KIOSK) document.body.classList.add("kiosk");

let asleep = false;
async function loadSleep() {
  if (!IS_KIOSK) return;
  try {
    const { data } = await getJSON("sleep", "/api/sleep");
    if (data.asleep === asleep) return;
    asleep = data.asleep;
    $("sleep").hidden = !asleep;
    if (!asleep) { loadCalendar(true); loadWeather(true); loadFitbit(); loadSpotify(); loadPackages(); }
  } catch (e) { console.warn(e); }
}
// Skip the network-heavy pollers while the screen is dark.
const whenAwake = (fn) => () => { if (!asleep) fn(); };

// ---------- boot ----------

(async () => {
  try {
    cfg = { ...cfg, ...(await (await fetch("/api/config")).json()) };
    if (cfg.background) $("bg").style.backgroundImage = `url("${cfg.background}")`;
    if (cfg.background_dim != null) $("bg").style.setProperty("--dim", cfg.background_dim);
  } catch (e) { console.warn(e); }

  tick();
  setInterval(tick, 1000);
  loadCalendar(); setInterval(loadCalendar, 5 * 60000);
  loadWeather();  setInterval(loadWeather, 15 * 60000);
  loadFitbit();   setInterval(whenAwake(loadFitbit), 5 * 60000);
  loadSpotify();  setInterval(whenAwake(loadSpotify), 10000);
  loadPackages(); setInterval(whenAwake(loadPackages), 5 * 60000);
  loadSleep();    setInterval(loadSleep, 30000);
})();
