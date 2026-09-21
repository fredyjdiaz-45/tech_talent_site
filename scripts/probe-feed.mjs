#!/usr/bin/env node
/** Diagnostic: find the real USDA shuttle feed. Runs on a GitHub runner. */
const HOSTS = (process.env.PROBE_HOSTS || 'https://usda.ridesystems.net').split(',');
const trunc = (s, n = 700) => (s.length > n ? s.slice(0, n) + ` … [+${s.length - n} chars]` : s);

async function hit(url, headers = {}) {
  try {
    const r = await fetch(url, { headers: { 'user-agent': 'Mozilla/5.0', ...headers }, redirect: 'follow' });
    const body = await r.text();
    return { status: r.status, finalUrl: r.url, server: r.headers.get('server'),
      cors: r.headers.get('access-control-allow-origin'), ctype: r.headers.get('content-type'), body };
  } catch (e) { return { error: e.message }; }
}

const PATHS = [
  // classic RideSystems JSONP relay
  '/Services/JSONPRelay.svc/GetMapVehiclePoints?APIKey=8882812681&isPublicMap=true',
  // modern RideSystems "InfoPoint" REST
  '/InfoPoint/',
  '/InfoPoint/rest/Vehicles/GetAllVehiclesForMap',
  '/InfoPoint/rest/Vehicles/GetAllVehiclesForMap?ApiKey=8882812681',
  '/InfoPoint/rest/Routes/GetVisibleRoutes',
  '/InfoPoint/rest/RouteDetails/GetAllRouteDetails',
  '/InfoPoint/rest/Stops/GetAllStops',
  '/InfoPoint/map'
];

async function main() {
  for (const base of HOSTS) {
    console.log('\n########## HOST', base, '##########');
    const root = await hit(base + '/');
    console.log('ROOT status', root.status, '| finalUrl', root.finalUrl, '| server', root.server, '| ctype', root.ctype);
    console.log('ROOT body:\n', trunc(root.body || root.error, 900));

    for (const p of PATHS) {
      const r = await hit(base + p, { origin: 'https://fredyjdiaz-45.github.io' });
      if (r.error) { console.log(`\n${p} -> ERR ${r.error}`); continue; }
      const looksJson = (r.ctype || '').includes('json') || /^[\[{]/.test((r.body || '').trim());
      console.log(`\n${p}\n  HTTP ${r.status} | ctype ${r.ctype} | CORS ${r.cors || '(none)'} | json=${looksJson}`);
      console.log('  body:', trunc((r.body || '').trim(), looksJson ? 600 : 160));
    }
  }
}
main().catch(e => { console.error('FATAL', e); process.exit(1); });
