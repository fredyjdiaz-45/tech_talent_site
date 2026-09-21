/* USDA GWCC <-> Greenbelt Shuttle
   Honest data model:
   - Predictions come from the OFFICIAL PUBLISHED SCHEDULE (real ARS timetable).
   - The map shows the real stop locations and route.
   - Live GPS vehicle positions are NOT publicly available for this shuttle; they
     live only inside the official "USDA Shuttle" app (authenticated). We link to it
     rather than fake a feed.
   - Performance is crowd-sourced from riders' own on-time / late logs (real, opt-in).
*/
'use strict';

const OFFICIAL_APP = {
  ios: 'https://apps.apple.com/us/app/usda-shuttle/id6742362538',
  android: 'https://play.google.com/store/apps/details?id=com.bishoppeaktech.android.usdashuttle'
};

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const pad = n => String(n).padStart(2, '0');

const state = { schedule: null, dir: 'to_greenbelt', map: null };

/* ---------- Eastern-Time helpers ---------- */
function etParts(d = new Date()) {
  const f = new Intl.DateTimeFormat('en-US', {
    timeZone: (state.schedule?.meta?.timezone) || 'America/New_York',
    weekday: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  });
  const p = Object.fromEntries(f.formatToParts(d).map(x => [x.type, x.value]));
  const dow = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }[p.weekday];
  let h = parseInt(p.hour, 10); if (h === 24) h = 0;
  return { h, m: parseInt(p.minute, 10), s: parseInt(p.second, 10), dow };
}
const nowMin = () => { const p = etParts(); return p.h * 60 + p.m + p.s / 60; };
const hhmmToMin = t => { const [h, m] = t.split(':').map(Number); return h * 60 + m; };
function minToLabel(mins) {
  mins = ((Math.round(mins) % 1440) + 1440) % 1440;
  const h = Math.floor(mins / 60), m = mins % 60, ap = h < 12 ? 'AM' : 'PM', h12 = (h % 12) || 12;
  return `${h12}:${pad(m)} ${ap}`;
}
const isServiceDay = () => (state.schedule?.meta?.serviceDays || [1, 2, 3, 4, 5]).includes(etParts().dow);

/* ---------- schedule model ---------- */
function departuresFor(dirId) {
  const d = state.schedule.directions[dirId];
  const first = hhmmToMin(d.firstDeparture), last = hhmmToMin(d.lastDeparture), step = d.headwayMinutes;
  const out = [];
  for (let t = first; t <= last + 0.001; t += step) out.push(Math.round(t));
  return out;
}
const TRIP_MIN = 10;

/* ---------- board ---------- */
function renderBoard() {
  const dir = state.dir, d = state.schedule.directions[dir];
  $('#heroRoute').innerHTML = `Next departure &nbsp;·&nbsp; <b>${d.label}</b>`;

  const service = isServiceDay(), cur = nowMin();
  const deps = departuresFor(dir), future = deps.filter(t => t >= cur - 0.5);
  const cd = $('#cdMain'), unit = $('#cdUnit');

  if (service && future.length) {
    const mins = Math.max(0, Math.round(future[0] - cur));
    cd.textContent = mins <= 0 ? 'Now' : String(mins);
    cd.appendChild(unit); unit.textContent = mins <= 0 ? '' : ' min';
    $('#cdLeaves').textContent = `Scheduled departure at ${minToLabel(future[0])}`;
    $('#upcomingList').innerHTML = future.slice(1, 6).map(t =>
      `<li><span class="t">${minToLabel(t)}</span><span class="rel">in ${Math.round(t - cur)} min</span></li>`).join('')
      || '<li><span class="rel">That is the last shuttle today.</span></li>';
  } else {
    cd.textContent = '—'; cd.appendChild(unit); unit.textContent = '';
    $('#cdLeaves').textContent = service ? 'Service has ended for today.' : 'No service today.';
    $('#upcomingList').innerHTML =
      `<li><span class="rel">First shuttle ${service ? 'tomorrow' : 'next weekday'}: ${minToLabel(deps[0])}</span></li>`;
  }
  $('#cdSrc').innerHTML = `<span class="badge">OFFICIAL SCHEDULE</span> ARS published timetable`;

  const sm = $('#serviceMsg');
  sm.textContent = !service
    ? 'The shuttle does not run on weekends or federal holidays.'
    : `Runs about every ${d.headwayMinutes} min, ${d.firstDeparture}–${d.lastDeparture}, weekdays (Eastern Time).`;

  const stats = [
    { kpi: `${d.headwayMinutes}<span style="font-size:16px"> min</span>`, lbl: 'Typical headway' },
    { kpi: minToLabel(deps[0]), lbl: 'First departure' },
    { kpi: minToLabel(deps[deps.length - 1]), lbl: 'Last departure' }
  ];
  $('#boardStats').innerHTML = stats.map(i =>
    `<div class="card stat"><div class="kpi">${i.kpi}</div><div class="lbl">${i.lbl}</div></div>`).join('');

  $('#boardDisclaimer').textContent = state.schedule.meta.source;
}

/* ---------- schedule table ---------- */
function renderSchedule() {
  const dir = $('#panel-schedule [data-dir][aria-pressed="true"]')?.dataset.dir || state.dir;
  const deps = departuresFor(dir), cur = nowMin(), service = isServiceDay();
  const nextIdx = deps.findIndex(t => t >= cur - 0.5);
  $('#schedBody').innerHTML = deps.map((t, i) => {
    const isNow = service && i === nextIdx;
    return `<tr class="${isNow ? 'now' : ''}"><td>${minToLabel(t)}${isNow ? '<span class="now-tag">NEXT</span>' : ''}</td>`
      + `<td>${minToLabel(t + TRIP_MIN)}</td><td></td></tr>`;
  }).join('');
  $('#schedNotes').innerHTML = (state.schedule.meta.notes || []).map(n => '• ' + n).join('<br>');
}

/* ---------- map (stops + route only; no live vehicles are publicly available) ---------- */
function initMap() {
  if (state.map || typeof L === 'undefined') return;
  const g = state.schedule.stops.greenbelt, w = state.schedule.stops.gwcc;
  const map = L.map('map', { scrollWheelZoom: false })
    .setView([(g.lat + w.lat) / 2, (g.lon + w.lon) / 2], 14);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(map);
  const icon = c => L.divIcon({ className: '', iconSize: [16, 16], iconAnchor: [8, 8],
    html: `<div style="width:16px;height:16px;border-radius:50%;background:${c};border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>` });
  L.polyline([[w.lat, w.lon], [g.lat, g.lon]], { color: '#0A2240', weight: 4, opacity: .5, dashArray: '6 6' }).addTo(map);
  L.marker([w.lat, w.lon], { icon: icon('#0A2240') }).addTo(map).bindPopup(`<b>${w.name}</b><br>${w.address}`);
  L.marker([g.lat, g.lon], { icon: icon('#1E7A46') }).addTo(map).bindPopup(`<b>${g.name}</b><br>${g.line} line`);
  state.map = map;
}

/* ---------- performance (crowd-sourced, real, per-device) ---------- */
const OBS_KEY = 'gwcc.observations.v1';
const loadObs = () => { try { return JSON.parse(localStorage.getItem(OBS_KEY)) || []; } catch { return []; } };
const saveObs = o => { try { localStorage.setItem(OBS_KEY, JSON.stringify(o.slice(-500))); } catch {} };
function addObs(onTime) {
  const p = etParts(), obs = loadObs();
  obs.push({ ts: Date.now(), hour: p.h, dir: state.dir, onTime: !!onTime });
  saveObs(obs); renderPerformance();
}
function renderPerformance() {
  const obs = loadObs();
  let onTimePct = null, byHour = null;
  if (obs.length) {
    onTimePct = Math.round(obs.filter(o => o.onTime).length / obs.length * 100);
    byHour = {};
    for (const o of obs) { byHour[o.hour] = byHour[o.hour] || { good: 0, total: 0 }; byHour[o.hour].total++; if (o.onTime) byHour[o.hour].good++; }
  }
  const cls = onTimePct == null ? '' : onTimePct >= 90 ? 'good' : onTimePct >= 75 ? 'warn' : 'bad';
  $('#perfStats').innerHTML = [
    { kpi: onTimePct == null ? '—' : onTimePct + '%', c: cls, lbl: 'On-time (your logs)' },
    { kpi: obs.length || '0', c: '', lbl: 'Rides logged' },
    { kpi: obs.filter(o => !o.onTime).length || '0', c: '', lbl: 'Late reports' },
    { kpi: 'This device', c: '', lbl: 'Source', small: true }
  ].map(i => `<div class="card stat"><div class="kpi ${i.c}" style="${i.small ? 'font-size:18px' : ''}">${i.kpi}</div><div class="lbl">${i.lbl}</div></div>`).join('');

  const chart = $('#perfChart');
  if (byHour) {
    let html = '';
    for (let h = 6; h <= 18; h++) {
      const v = byHour[h], pct = v && v.total ? Math.round(v.good / v.total * 100) : null;
      const c = pct == null ? '' : pct >= 90 ? 'good' : pct >= 75 ? 'warn' : 'bad';
      html += `<div class="bar ${c}" style="height:${pct == null ? 2 : Math.max(4, pct)}%" title="${h}:00 — ${pct == null ? 'no data' : pct + '% on time'}"></div>`;
    }
    chart.innerHTML = html;
  } else {
    chart.innerHTML = '<p class="small" style="align-self:center;margin:auto">No rides logged yet — use the buttons below as you ride.</p>';
  }
  $('#obsCount').textContent = obs.length ? `${obs.length} ride(s) logged on this device.` : 'No rides logged yet.';
}

/* ---------- tabs / wiring ---------- */
function showTab(name) {
  $$('nav.tabs button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
  $$('.panel').forEach(p => p.hidden = (p.id !== 'panel-' + name));
  if (name === 'map') { initMap(); setTimeout(() => state.map && state.map.invalidateSize(), 60); }
  if (name === 'schedule') renderSchedule();
  if (name === 'performance') renderPerformance();
}
function wire() {
  $$('nav.tabs button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
  $$('#panel-board [data-dir]').forEach(b => b.addEventListener('click', () => {
    state.dir = b.dataset.dir;
    $$('#panel-board [data-dir]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    renderBoard();
  }));
  $$('#panel-schedule [data-dir]').forEach(b => b.addEventListener('click', () => {
    $$('#panel-schedule [data-dir]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    renderSchedule();
  }));
  $('#logOnTime').addEventListener('click', () => addObs(true));
  $('#logLate').addEventListener('click', () => addObs(false));
  $('#clearObs').addEventListener('click', () => { saveObs([]); renderPerformance(); });

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

  // official-app links
  $$('[data-app="ios"]').forEach(a => a.href = OFFICIAL_APP.ios);
  $$('[data-app="android"]').forEach(a => a.href = OFFICIAL_APP.android);
}

async function boot() {
  wire();
  try {
    const r = await fetch('schedule.json'); state.schedule = await r.json();
  } catch (e) {
    $('#modeText').textContent = 'Data error';
    $('#serviceMsg').textContent = 'Could not load schedule data.';
    return;
  }
  $('#modeDot').className = 'dot sched';
  $('#modeText').textContent = 'Official schedule';
  renderBoard();
  renderPerformance();
  setInterval(renderBoard, 15000); // keep the countdown fresh
}
document.addEventListener('DOMContentLoaded', boot);
