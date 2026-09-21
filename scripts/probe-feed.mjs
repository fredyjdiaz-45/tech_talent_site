#!/usr/bin/env node
/**
 * One-off diagnostic: discover the real USDA Ride Systems feed shape.
 * Runs on a GitHub Actions runner (open network). Prints findings to the log:
 *   - candidate API keys scraped from the public map page
 *   - which JSONPRelay.svc endpoints respond, with a truncated body sample
 *   - whether the endpoints send CORS headers (fetch from a browser) and/or
 *     support JSONP (?callback=), which decides how the static app must call them
 */
const BASE = process.env.RIDESYSTEMS_BASE || 'https://usda.ridesystems.net';
const ORIGIN = 'https://fredyjdiaz-45.github.io';
const trunc = (s, n = 600) => (s.length > n ? s.slice(0, n) + ` … [+${s.length - n} chars]` : s);

async function text(url, headers = {}) {
  const r = await fetch(url, { headers, redirect: 'follow' });
  return { status: r.status, headers: r.headers, body: await r.text() };
}

function scrapeKeys(html) {
  const keys = new Set();
  const pats = [
    /ApiKey["'\s:=]+["']?([0-9]{6,})/gi,
    /apikey=([0-9]{6,})/gi,
    /"key"\s*:\s*"([0-9]{6,})"/gi,
    /InitMap\([^)]*?([0-9]{9,})/gi
  ];
  for (const p of pats) { let m; while ((m = p.exec(html))) keys.add(m[1]); }
  return [...keys];
}

async function main() {
  console.log('=== BASE', BASE, '===');

  // 1) scrape the public map page(s) for API keys
  let html = '';
  for (const path of ['/', '/Home/Map', '/InfoPoint', '/routes']) {
    try {
      const r = await text(BASE + path, { 'user-agent': 'Mozilla/5.0' });
      console.log(`page ${path}: HTTP ${r.status}, ${r.body.length} bytes`);
      if (r.status === 200) html += '\n' + r.body;
    } catch (e) { console.log(`page ${path}: ERR ${e.message}`); }
  }
  const scraped = scrapeKeys(html);
  console.log('scraped key candidates:', scraped);

  const keys = [...new Set([...scraped, '8882812681', '1132363162', '8882812681'])];
  const methods = ['GetMapVehiclePoints', 'GetRoutes', 'GetStops',
                   'GetStopArrivalTimes', 'GetRoutesForMapWithScheduleWithEncodedLine'];

  // 2) find a working key using the vehicle-points endpoint
  let goodKey = null;
  for (const k of keys) {
    const url = `${BASE}/Services/JSONPRelay.svc/GetMapVehiclePoints?APIKey=${k}&isPublicMap=true`;
    try {
      const r = await text(url, { origin: ORIGIN });
      const ok = r.status === 200 && r.body.trim().startsWith('[');
      console.log(`key ${k}: GetMapVehiclePoints HTTP ${r.status} ${ok ? 'JSON-array OK' : 'not-array'} :: ${trunc(r.body, 200)}`);
      if (ok && !goodKey) goodKey = k;
    } catch (e) { console.log(`key ${k}: ERR ${e.message}`); }
  }
  console.log('>>> WORKING KEY:', goodKey);
  if (!goodKey) return;

  // 3) dump each endpoint's shape
  for (const m of methods) {
    const url = `${BASE}/Services/JSONPRelay.svc/${m}?APIKey=${goodKey}`;
    try {
      const r = await text(url, { origin: ORIGIN });
      console.log(`\n--- ${m} (HTTP ${r.status}) ---`);
      console.log('CORS allow-origin:', r.headers.get('access-control-allow-origin') || '(none)');
      console.log('body:', trunc(r.body, 900));
    } catch (e) { console.log(`${m}: ERR ${e.message}`); }
  }

  // 4) does the service support JSONP? (decides browser call strategy)
  try {
    const url = `${BASE}/Services/JSONPRelay.svc/GetMapVehiclePoints?APIKey=${goodKey}&isPublicMap=true&callback=__cb`;
    const r = await text(url);
    console.log('\n--- JSONP test ---');
    console.log('starts with __cb(?', r.body.trimStart().startsWith('__cb('), ':: ', trunc(r.body, 120));
  } catch (e) { console.log('JSONP test ERR', e.message); }
}
main().catch(e => { console.error('FATAL', e); process.exit(1); });
