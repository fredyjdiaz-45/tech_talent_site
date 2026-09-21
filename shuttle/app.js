/* USDA GWCC <-> Greenbelt Shuttle Tracker
   Self-contained client app. Two data modes:
     - schedule  : always available; next departures computed from schedule.json
     - live      : Ride Systems GPS feed (client-side fetch), upgrades the board + map
   Performance:  central data/performance.json when present, plus per-device observations.
*/
'use strict';

const CFG = {
  apiBaseDefault: 'https://usda.ridesystems.net',
  // Common public Ride Systems key; override in About > Live data settings if needed.
  apiKeyDefault: '8882812681',
  scheduleUrl: 'schedule.json',
  performanceUrl: '../data/performance.json',
  liveRefreshMs: 20000,
  clockRefreshMs: 1000,
  onTimeWindowMin: 5,          // within +/- N min of schedule counts as on-time
  matchStopKeywords: {
    gwcc: ['carver', 'gwcc', 'sunnyside'],
    greenbelt: ['greenbelt', 'metro']
  }
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const pad = n => String(n).padStart(2, '0');

const state = {
  schedule: null,
  dir: 'to_greenbelt',
  api: {
    key: localStorage.getItem('gwcc.apiKey') || CFG.apiKeyDefault,
    base: localStorage.getItem('gwcc.apiBase') || CFG.apiBaseDefault
  },
  mode: 'loading',      // loading | live | schedule | offline
  vehicles: [],
  liveEtas: null,       // { to_greenbelt:[minutes...], to_gwcc:[...] } or null
  map: null,
  markers: {},
  perf: null
};

/* ---------- time helpers (Eastern Time) ---------- */
function etParts(d = new Date()) {
  const f = new Intl.DateTimeFormat('en-US', {
    timeZone: CFG.schedule?.timezone || 'America/New_York',
    weekday: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  });
  const p = Object.fromEntries(f.formatToParts(d).map(x => [x.type, x.value]));
  const dowMap = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  let h = parseInt(p.hour, 10); if (h === 24) h = 0;
  return { h, m: parseInt(p.minute, 10), s: parseInt(p.second, 10), dow: dowMap[p.weekday] };
}
const nowMin = () => { const p = etParts(); return p.h * 60 + p.m + p.s / 60; };
const hhmmToMin = t => { const [h, m] = t.split(':').map(Number); return h * 60 + m; };
function minToLabel(mins) {
  mins = ((Math.round(mins) % 1440) + 1440) % 1440;
  const h = Math.floor(mins / 60), m = mins % 60;
  const ap = h < 12 ? 'AM' : 'PM'; const h12 = (h % 12) || 12;
  return `${h12}:${pad(m)} ${ap}`;
}
function isServiceDay() {
  const days = state.schedule?.meta?.serviceDays || [1, 2, 3, 4, 5];
  return days.includes(etParts().dow);
}

/* ---------- schedule model ---------- */
function departuresFor(dirId) {
  const d = state.schedule.directions[dirId];
  const first = hhmmToMin(d.firstDeparture), last = hhmmToMin(d.lastDeparture);
  const step = d.headwayMinutes;
  const out = [];
  for (let t = first; t <= last + 0.001; t += step) out.push(Math.round(t));
  return out;
}
const TRIP_MIN = 10;

/* ---------- rendering: board ---------- */
function renderBoard() {
  const dir = state.dir;
  const d = state.schedule.directions[dir];
  $('#heroRoute').innerHTML = `Next departure &nbsp;·&nbsp; <b>${d.label}</b>`;

  const service = isServiceDay();
  const cur = nowMin();
  const deps = departuresFor(dir);
  const future = deps.filter(t => t >= cur - 0.5);

  // live ETA (minutes-from-now) list for this direction, if present
  const live = state.mode === 'live' && state.liveEtas && state.liveEtas[dir]?.length
    ? state.liveEtas[dir].slice().sort((a, b) => a - b) : null;

  const cdMain = $('#cdMain'), cdUnit = $('#cdUnit'), cdLeaves = $('#cdLeaves'), cdSrc = $('#cdSrc');
  const upList = $('#upcomingList');

  if (live) {
    const next = live[0];
    setCountdown(next);
    cdLeaves.textContent = `Live ETA · arrives about ${minToLabel(cur + next)}`;
    cdSrc.innerHTML = `<span class="badge live">LIVE</span> from GPS vehicle feed`;
    upList.innerHTML = live.slice(1, 6).map(mn =>
      `<li><span class="t">${minToLabel(cur + mn)}</span><span class="rel">in ${Math.max(0, Math.round(mn))} min</span></li>`).join('')
      || '<li><span class="rel">No further live arrivals.</span></li>';
  } else if (service && future.length) {
    const next = future[0] - cur;
    setCountdown(next);
    cdLeaves.textContent = `Scheduled · leaves ${minToLabel(future[0])}`;
    cdSrc.innerHTML = `<span class="badge">SCHEDULE</span> based on published timetable`;
    upList.innerHTML = future.slice(1, 6).map(t =>
      `<li><span class="t">${minToLabel(t)}</span><span class="rel">in ${Math.round(t - cur)} min</span></li>`).join('')
      || '<li><span class="rel">Last shuttle of the day has left.</span></li>';
  } else {
    cdMain.textContent = '—'; cdUnit.textContent = '';
    cdLeaves.textContent = service ? 'Service has ended for today.' : 'No service today.';
    cdSrc.innerHTML = `<span class="badge">SCHEDULE</span>`;
    const nextDay = service ? 'tomorrow' : 'the next weekday';
    upList.innerHTML = `<li><span class="rel">First shuttle ${nextDay}: ${minToLabel(deps[0])}</span></li>`;
  }

  // service message
  const sm = $('#serviceMsg');
  if (!service) sm.textContent = 'The shuttle does not run on weekends or federal holidays.';
  else if (!future.length) sm.textContent = `Today's service window: ${d.firstDeparture} – ${d.lastDeparture}.`;
  else sm.textContent = `Runs about every ${d.headwayMinutes} min, ${d.firstDeparture}–${d.lastDeparture}, weekdays.`;

  renderBoardStats();
  $('#boardDisclaimer').textContent = state.schedule.meta.source;
}
function setCountdown(mins) {
  const cd = $('#cdMain'), unit = $('#cdUnit');
  const m = Math.max(0, Math.round(mins));
  if (m <= 0) { cd.textContent = 'Now'; unit.textContent = ''; cd.appendChild(unit); return; }
  cd.textContent = m; cd.appendChild(unit); unit.textContent = m === 1 ? ' min' : ' min';
}

function renderBoardStats() {
  const g = state.schedule.stops.greenbelt, w = state.schedule.stops.gwcc;
  const items = [
    { kpi: `${state.schedule.directions[state.dir].headwayMinutes}<span style="font-size:16px"> min</span>`, lbl: 'Typical headway' },
    { kpi: liveVehicleCount() != null ? liveVehicleCount() : '—', lbl: 'Shuttles live now' },
    { kpi: `~${TRIP_MIN} min`, lbl: 'Ride time GWCC↔Greenbelt' }
  ];
  $('#boardStats').innerHTML = items.map(i =>
    `<div class="card stat"><div class="kpi">${i.kpi}</div><div class="lbl">${i.lbl}</div></div>`).join('');
}
function liveVehicleCount() { return state.mode === 'live' ? state.vehicles.length : null; }

/* ---------- rendering: schedule table ---------- */
function renderSchedule() {
  const dir = $('#panel-schedule [data-dir][aria-pressed="true"]')?.dataset.dir || state.dir;
  const d = state.schedule.directions[dir];
  const deps = departuresFor(dir);
  const cur = nowMin(); const service = isServiceDay();
  let nextIdx = deps.findIndex(t => t >= cur - 0.5);
  $('#schedBody').innerHTML = deps.map((t, i) => {
    const isNow = service && i === nextIdx;
    return `<tr class="${isNow ? 'now' : ''}"><td>${minToLabel(t)}${isNow ? '<span class="now-tag">NEXT</span>' : ''}</td>`
      + `<td>${minToLabel(t + TRIP_MIN)}</td><td></td></tr>`;
  }).join('');
  $('#schedNotes').innerHTML = (state.schedule.meta.notes || []).map(n => '• ' + n).join('<br>');
}

/* ---------- live feed (Ride Systems) ---------- */
function apiUrl(method, params = {}) {
  const u = new URL(`/Services/JSONPRelay.svc/${method}`, state.api.base);
  u.searchParams.set('APIKey', state.api.key);
  Object.entries(params).forEach(([k, v]) => u.searchParams.set(k, v));
  return u.toString();
}
async function getJSON(url) {
  const r = await fetch(url, { mode: 'cors', credentials: 'omit' });
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}
async function refreshLive() {
  try {
    const vehicles = await getJSON(apiUrl('GetMapVehiclePoints', { isPublicMap: 'true' }));
    state.vehicles = (Array.isArray(vehicles) ? vehicles : []).map(normVehicle).filter(Boolean);
    // best-effort ETAs
    try { state.liveEtas = await fetchEtas(); } catch { state.liveEtas = null; }
    setMode(state.vehicles.length || state.liveEtas ? 'live' : 'schedule');
  } catch (e) {
    state.vehicles = []; state.liveEtas = null;
    setMode('schedule');
  }
  renderBoard(); updateMap(); logLiveSample();
}
function normVehicle(v) {
  const lat = v.Latitude ?? v.latitude ?? v.lat;
  const lon = v.Longitude ?? v.longitude ?? v.lng ?? v.lon;
  if (typeof lat !== 'number' || typeof lon !== 'number') return null;
  return {
    id: v.VehicleID ?? v.ID ?? v.Name ?? Math.random(),
    name: v.Name ?? v.VehicleName ?? 'Shuttle',
    lat, lon,
    heading: v.Heading ?? 0,
    speed: v.GroundSpeed ?? v.Speed ?? null,
    routeId: v.RouteID ?? v.routeId ?? null
  };
}
// Try to derive minutes-to-arrival per direction from stop estimates. Tolerant of shape.
async function fetchEtas() {
  let data;
  try { data = await getJSON(apiUrl('GetStopArrivalTimes')); }
  catch { data = await getJSON(apiUrl('GetStopEstimates')); }
  const flat = flattenEstimates(data);
  const result = { to_greenbelt: [], to_gwcc: [] };
  for (const e of flat) {
    const name = (e.stopName || '').toLowerCase();
    const mins = e.minutes;
    if (mins == null || isNaN(mins)) continue;
    if (CFG.matchStopKeywords.greenbelt.some(k => name.includes(k))) result.to_gwcc.push(mins); // arriving at Greenbelt = heading toward... origin greenbelt: next bus from greenbelt
    if (CFG.matchStopKeywords.gwcc.some(k => name.includes(k))) result.to_greenbelt.push(mins);
  }
  return (result.to_greenbelt.length || result.to_gwcc.length) ? result : null;
}
function flattenEstimates(data) {
  const out = [];
  const visit = (node, stopName) => {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { node.forEach(n => visit(n, stopName)); return; }
    const sName = node.Description ?? node.StopName ?? node.Name ?? stopName;
    // find a minutes-ish value
    let mins = null;
    if (node.Seconds != null) mins = Number(node.Seconds) / 60;
    else if (node.Minutes != null) mins = Number(node.Minutes);
    else if (node.EstimateTime != null) mins = Number(node.EstimateTime);
    else if (typeof node.Text === 'string') { const mt = node.Text.match(/(\d+)\s*min/i); if (mt) mins = Number(mt[1]); }
    if (mins != null && sName) out.push({ stopName: String(sName), minutes: mins });
    for (const k in node) if (typeof node[k] === 'object') visit(node[k], sName);
  };
  visit(data, null);
  return out;
}

function setMode(mode) {
  state.mode = mode;
  const dot = $('#modeDot'), txt = $('#modeText');
  dot.className = 'dot ' + (mode === 'live' ? 'live' : mode === 'schedule' ? 'sched' : 'off');
  txt.textContent = mode === 'live' ? 'Live GPS' : mode === 'schedule' ? 'Schedule mode' : 'Loading…';
}

/* ---------- map ---------- */
function initMap() {
  if (state.map || typeof L === 'undefined') return;
  const g = state.schedule.stops.greenbelt, w = state.schedule.stops.gwcc;
  const map = L.map('map', { scrollWheelZoom: false })
    .setView([(g.lat + w.lat) / 2, (g.lon + w.lon) / 2], 14);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '© OpenStreetMap'
  }).addTo(map);
  const stopIcon = c => L.divIcon({ className: '', html:
    `<div style="width:16px;height:16px;border-radius:50%;background:${c};border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>`,
    iconSize: [16, 16], iconAnchor: [8, 8] });
  L.marker([w.lat, w.lon], { icon: stopIcon('#0A2240') }).addTo(map).bindPopup(`<b>${w.name}</b><br>${w.address}`);
  L.marker([g.lat, g.lon], { icon: stopIcon('#1E7A46') }).addTo(map).bindPopup(`<b>${g.name}</b><br>${g.line} line`);
  state.map = map;
  updateMap();
}
function busIcon(heading) {
  return L.divIcon({ className: '', iconSize: [26, 26], iconAnchor: [13, 13], html:
    `<div style="width:26px;height:26px;border-radius:50%;background:#D6202F;border:3px solid #fff;box-shadow:0 1px 5px rgba(0,0,0,.5);
      display:grid;place-items:center;transform:rotate(${heading || 0}deg)">
      <div style="width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-bottom:9px solid #fff"></div></div>` });
}
function updateMap() {
  if (!state.map) return;
  const seen = new Set();
  for (const v of state.vehicles) {
    seen.add(v.id);
    const ll = [v.lat, v.lon];
    if (state.markers[v.id]) { state.markers[v.id].setLatLng(ll).setIcon(busIcon(v.heading)); }
    else state.markers[v.id] = L.marker(ll, { icon: busIcon(v.heading) })
      .addTo(state.map).bindPopup(`<b>${v.name}</b>${v.speed != null ? '<br>' + Math.round(v.speed) + ' mph' : ''}`);
  }
  Object.keys(state.markers).forEach(id => {
    if (!seen.has(id) && !seen.has(Number(id))) { state.map.removeLayer(state.markers[id]); delete state.markers[id]; }
  });
  const msg = $('#mapMsg');
  if (state.mode === 'live') msg.textContent = state.vehicles.length
    ? `${state.vehicles.length} shuttle(s) live · updates every ${CFG.liveRefreshMs / 1000}s.`
    : 'Connected to live feed, but no shuttles are reporting right now.';
  else msg.textContent = 'Live vehicle feed unavailable in this network — showing stops only. See About › Live data settings.';
}

/* ---------- performance ---------- */
const OBS_KEY = 'gwcc.observations.v1';
function loadObs() { try { return JSON.parse(localStorage.getItem(OBS_KEY)) || []; } catch { return []; } }
function saveObs(o) { try { localStorage.setItem(OBS_KEY, JSON.stringify(o.slice(-500))); } catch {} }
function addObs(onTime) {
  const p = etParts();
  const obs = loadObs();
  obs.push({ ts: Date.now(), hour: p.h, dir: state.dir, onTime: !!onTime });
  saveObs(obs); renderPerformance();
}
// passively record a live sample as an observation of headway adherence (best-effort)
function logLiveSample() {
  if (state.mode !== 'live' || !state.liveEtas) return;
  // keep lightweight: no-op placeholder for future central logging
}
async function loadCentralPerf() {
  try { state.perf = await getJSON(CFG.performanceUrl); } catch { state.perf = null; }
}
function renderPerformance() {
  const obs = loadObs();
  const central = state.perf && state.perf.summary && state.perf.summary.samples > 0 ? state.perf : null;

  let onTimePct, sample, avgWaitTxt, sourceLbl, byHour;
  if (central) {
    onTimePct = central.summary.onTimePct;
    sample = central.summary.samples;
    avgWaitTxt = central.summary.avgWaitMin != null ? central.summary.avgWaitMin + ' min' : '—';
    sourceLbl = 'Automated monitor';
    byHour = central.byHour || null;
  } else if (obs.length) {
    const good = obs.filter(o => o.onTime).length;
    onTimePct = Math.round(good / obs.length * 100);
    sample = obs.length;
    avgWaitTxt = (state.schedule.directions[state.dir].headwayMinutes / 2) + ' min (est.)';
    sourceLbl = 'Your device';
    byHour = hourBuckets(obs);
  } else {
    onTimePct = null; sample = 0; avgWaitTxt = '—'; sourceLbl = 'No data yet'; byHour = null;
  }

  const cls = onTimePct == null ? '' : onTimePct >= 90 ? 'good' : onTimePct >= 75 ? 'warn' : 'bad';
  $('#perfStats').innerHTML = [
    { kpi: onTimePct == null ? '—' : onTimePct + '%', c: cls, lbl: 'On-time (±' + CFG.onTimeWindowMin + ' min)' },
    { kpi: avgWaitTxt, c: '', lbl: 'Avg wait' },
    { kpi: sample || '0', c: '', lbl: 'Samples' },
    { kpi: sourceLbl, c: '', lbl: 'Source', small: true }
  ].map(i => `<div class="card stat"><div class="kpi ${i.c}" style="${i.small ? 'font-size:18px' : ''}">${i.kpi}</div><div class="lbl">${i.lbl}</div></div>`).join('');

  // hour chart 6..18
  const chart = $('#perfChart');
  if (byHour) {
    let html = '';
    for (let h = 6; h <= 18; h++) {
      const v = byHour[h];
      const pct = v && v.total ? Math.round(v.good / v.total * 100) : null;
      const height = pct == null ? 2 : Math.max(4, pct);
      const c = pct == null ? '' : pct >= 90 ? 'good' : pct >= 75 ? 'warn' : 'bad';
      html += `<div class="bar ${c}" style="height:${height}%" title="${h}:00 — ${pct == null ? 'no data' : pct + '% on time'}"></div>`;
    }
    chart.innerHTML = html;
  } else {
    chart.innerHTML = '<p class="small" style="align-self:center;margin:auto">No hourly data yet.</p>';
  }

  $('#obsCount').textContent = obs.length
    ? `${obs.length} observation(s) logged on this device.`
    : 'No observations logged yet.';
}
function hourBuckets(obs) {
  const b = {};
  for (const o of obs) { const h = o.hour; b[h] = b[h] || { good: 0, total: 0 }; b[h].total++; if (o.onTime) b[h].good++; }
  return b;
}

/* ---------- tabs / toggles / wiring ---------- */
function showTab(name) {
  $$('nav.tabs button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
  $$('.panel').forEach(p => p.hidden = (p.id !== 'panel-' + name));
  if (name === 'map') { initMap(); setTimeout(() => state.map && state.map.invalidateSize(), 60); }
  if (name === 'schedule') renderSchedule();
  if (name === 'performance') renderPerformance();
}
function wire() {
  $$('nav.tabs button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));

  // direction toggles (board + schedule share concept)
  $$('#panel-board [data-dir]').forEach(b => b.addEventListener('click', () => {
    state.dir = b.dataset.dir;
    $$('#panel-board [data-dir]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    renderBoard();
  }));
  $$('#panel-schedule [data-dir]').forEach(b => b.addEventListener('click', () => {
    $$('#panel-schedule [data-dir]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    renderSchedule();
  }));

  // performance buttons
  $('#logOnTime').addEventListener('click', () => addObs(true));
  $('#logLate').addEventListener('click', () => addObs(false));
  $('#clearObs').addEventListener('click', () => { saveObs([]); renderPerformance(); });

  // api settings
  $('#apiKey').value = state.api.key;
  $('#apiBase').value = state.api.base;
  $('#saveApi').addEventListener('click', () => {
    state.api.key = $('#apiKey').value.trim() || CFG.apiKeyDefault;
    state.api.base = $('#apiBase').value.trim() || CFG.apiBaseDefault;
    localStorage.setItem('gwcc.apiKey', state.api.key);
    localStorage.setItem('gwcc.apiBase', state.api.base);
    refreshLive();
  });
  $('#resetApi').addEventListener('click', () => {
    localStorage.removeItem('gwcc.apiKey'); localStorage.removeItem('gwcc.apiBase');
    state.api = { key: CFG.apiKeyDefault, base: CFG.apiBaseDefault };
    $('#apiKey').value = state.api.key; $('#apiBase').value = state.api.base;
    refreshLive();
  });

  // theme
  const savedTheme = localStorage.getItem('gwcc.theme');
  if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);
  $('#themeToggle').addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme');
    const isDark = cur === 'dark' || (!cur && matchMedia('(prefers-color-scheme: dark)').matches);
    const next = isDark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('gwcc.theme', next);
    if (state.map) setTimeout(() => state.map.invalidateSize(), 50);
  });

  // ?apikey= / ?base= overrides
  const q = new URLSearchParams(location.search);
  if (q.get('apikey')) state.api.key = q.get('apikey');
  if (q.get('base')) state.api.base = q.get('base');
}

/* ---------- boot ---------- */
async function boot() {
  wire();
  try {
    state.schedule = await getJSON(CFG.scheduleUrl);
  } catch (e) {
    setMode('offline');
    $('#serviceMsg').textContent = 'Could not load schedule data.';
    return;
  }
  CFG.schedule = state.schedule.meta;
  setMode('schedule');
  renderBoard();
  await loadCentralPerf();
  renderPerformance();

  refreshLive();
  setInterval(refreshLive, CFG.liveRefreshMs);
  setInterval(() => { renderBoard(); }, CFG.clockRefreshMs * 10); // refresh countdown ~10s
}
document.addEventListener('DOMContentLoaded', boot);
