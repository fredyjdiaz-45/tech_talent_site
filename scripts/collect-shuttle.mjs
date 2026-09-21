#!/usr/bin/env node
/**
 * USDA GWCC <-> Greenbelt shuttle performance collector.
 *
 * Runs on a schedule (GitHub Actions). Polls the Ride Systems live GPS feed,
 * records one sample per run to data/samples.ndjson, and recomputes the public
 * rollup at data/performance.json that the web app reads.
 *
 * Network note: this must run somewhere with open outbound access to
 * usda.ridesystems.net (GitHub-hosted runners work; some corporate/sandbox
 * networks block it). No API key secret required for the public map feed, but
 * one can be supplied via the RIDESYSTEMS_APIKEY env var.
 *
 * Usage:  node scripts/collect-shuttle.mjs
 */
import { readFile, writeFile, appendFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const SCHEDULE = path.join(ROOT, 'shuttle', 'schedule.json');
const DATA_DIR = path.join(ROOT, 'data');
const SAMPLES = path.join(DATA_DIR, 'samples.ndjson');
const ROLLUP = path.join(DATA_DIR, 'performance.json');

const API_BASE = process.env.RIDESYSTEMS_BASE || 'https://usda.ridesystems.net';
const API_KEY = process.env.RIDESYSTEMS_APIKEY || '8882812681';
const ON_TIME_WINDOW = 5; // minutes

const KEYWORDS = {
  gwcc: ['carver', 'gwcc', 'sunnyside'],
  greenbelt: ['greenbelt', 'metro']
};

const now = new Date();
const etParts = () => {
  const f = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false
  });
  const p = Object.fromEntries(f.formatToParts(now).map(x => [x.type, x.value]));
  const dow = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }[p.weekday];
  let h = parseInt(p.hour, 10); if (h === 24) h = 0;
  return { h, m: parseInt(p.minute, 10), dow };
};

async function getJSON(url) {
  const r = await fetch(url, { headers: { accept: 'application/json' } });
  if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
  return r.json();
}
const api = (method, params = {}) => {
  const u = new URL(`/Services/JSONPRelay.svc/${method}`, API_BASE);
  u.searchParams.set('APIKey', API_KEY);
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v);
  return u.toString();
};

function flattenEstimates(data) {
  const out = [];
  const visit = (node, stopName) => {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.forEach(n => visit(n, stopName));
    const sName = node.Description ?? node.StopName ?? node.Name ?? stopName;
    let mins = null;
    if (node.Seconds != null) mins = Number(node.Seconds) / 60;
    else if (node.Minutes != null) mins = Number(node.Minutes);
    else if (node.EstimateTime != null) mins = Number(node.EstimateTime);
    else if (typeof node.Text === 'string') { const mt = node.Text.match(/(\d+)\s*min/i); if (mt) mins = Number(mt[1]); }
    if (mins != null && sName) out.push({ stopName: String(sName).toLowerCase(), minutes: mins });
    for (const k in node) if (typeof node[k] === 'object') visit(node[k], sName);
  };
  visit(data, null);
  return out;
}

async function collect() {
  const schedule = JSON.parse(await readFile(SCHEDULE, 'utf8'));
  const { h, m, dow } = etParts();
  const inService = (schedule.meta.serviceDays || [1, 2, 3, 4, 5]).includes(dow) && h >= 6 && (h < 18 || (h === 18 && m <= 20));

  const sample = { ts: now.toISOString(), hour: h, dow, inService, ok: false, vehicles: 0, minEta: {} };

  try {
    const vehicles = await getJSON(api('GetMapVehiclePoints', { isPublicMap: 'true' }));
    sample.vehicles = Array.isArray(vehicles) ? vehicles.length : 0;
    sample.ok = true;
    try {
      let est;
      try { est = await getJSON(api('GetStopArrivalTimes')); }
      catch { est = await getJSON(api('GetStopEstimates')); }
      const flat = flattenEstimates(est);
      const min = kws => {
        const xs = flat.filter(e => kws.some(k => e.stopName.includes(k))).map(e => e.minutes);
        return xs.length ? Math.min(...xs) : null;
      };
      sample.minEta.greenbelt = min(KEYWORDS.greenbelt);
      sample.minEta.gwcc = min(KEYWORDS.gwcc);
    } catch (e) { sample.etaError = String(e.message || e); }
  } catch (e) {
    sample.error = String(e.message || e);
  }

  await mkdir(DATA_DIR, { recursive: true });
  await appendFile(SAMPLES, JSON.stringify(sample) + '\n');
  await rollup(schedule);
  console.log('sample:', JSON.stringify(sample));
}

async function rollup(schedule) {
  if (!existsSync(SAMPLES)) return;
  const lines = (await readFile(SAMPLES, 'utf8')).trim().split('\n').filter(Boolean);
  const samples = lines.map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
  const headway = schedule.directions.to_greenbelt.headwayMinutes || 20;
  const threshold = headway + ON_TIME_WINDOW;

  // "on time" for a service-hours poll = a shuttle is arriving within one headway + window
  const svc = samples.filter(s => s.inService && s.ok);
  const scored = svc.map(s => {
    const etas = [s.minEta?.greenbelt, s.minEta?.gwcc].filter(v => v != null);
    const nextEta = etas.length ? Math.min(...etas) : null;
    const covered = s.vehicles > 0;              // at least one shuttle running
    const onTime = nextEta != null ? nextEta <= threshold : covered;
    return { hour: s.hour, onTime, covered, nextEta };
  });

  const good = scored.filter(s => s.onTime).length;
  const waits = scored.map(s => s.nextEta).filter(v => v != null);
  const byHour = {};
  for (const s of scored) { byHour[s.hour] = byHour[s.hour] || { good: 0, total: 0 }; byHour[s.hour].total++; if (s.onTime) byHour[s.hour].good++; }

  const out = {
    generatedAt: new Date().toISOString(),
    window: `${ON_TIME_WINDOW} min`,
    summary: {
      samples: scored.length,
      onTimePct: scored.length ? Math.round(good / scored.length * 100) : null,
      avgWaitMin: waits.length ? Math.round(waits.reduce((a, b) => a + b, 0) / waits.length * 10) / 10 : null,
      coveragePct: scored.length ? Math.round(scored.filter(s => s.covered).length / scored.length * 100) : null
    },
    byHour
  };
  await writeFile(ROLLUP, JSON.stringify(out, null, 2) + '\n');
}

collect().catch(e => { console.error(e); process.exit(1); });
