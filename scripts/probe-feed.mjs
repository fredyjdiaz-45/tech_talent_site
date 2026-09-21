#!/usr/bin/env node
/** Diagnostic v3: locate the USDA BusWhere shuttle viewer + its public data endpoint. */
const ORIGIN = 'https://fredyjdiaz-45.github.io';
const trunc = (s, n = 500) => (s.length > n ? s.slice(0, n) + ` … [+${s.length - n}]` : s);

async function hit(url, headers = {}) {
  try {
    const r = await fetch(url, { headers: { 'user-agent': 'Mozilla/5.0', ...headers }, redirect: 'follow' });
    return { status: r.status, finalUrl: r.url, cors: r.headers.get('access-control-allow-origin'),
      ctype: r.headers.get('content-type'), body: await r.text() };
  } catch (e) { return { error: e.message }; }
}
function urlsIn(html) {
  const set = new Set();
  for (const m of html.matchAll(/(?:src|href)=["']([^"']+)["']/gi)) set.add(m[1]);
  for (const m of html.matchAll(/["'](https?:\/\/[^"']+|\/[A-Za-z0-9_\-\/.]+\.(?:js|json))["']/gi)) set.add(m[1]);
  return [...set];
}
function apiHints(text) {
  const set = new Set();
  for (const m of text.matchAll(/["'`](\/?[A-Za-z0-9_\-\/.]*(?:api|service|vehicle|bus|location|route|feed|realtime|positions?)[A-Za-z0-9_\-\/.?=&]*)["'`]/gi)) set.add(m[1]);
  for (const m of text.matchAll(/(https?:\/\/[A-Za-z0-9_.\-]+\.(?:com|net|io)[A-Za-z0-9_\-\/.?=&]*)/gi)) set.add(m[1]);
  return [...set].filter(s => s.length < 160).slice(0, 40);
}

async function main() {
  // 1) reference: a known-good public shuttle viewer, to learn the data endpoint pattern
  console.log('===== REFERENCE: GWU public shuttle viewer =====');
  const ref = await hit('https://buswhere.com/GWU/routes/gw_vstc');
  console.log('status', ref.status, '| finalUrl', ref.finalUrl, '| ctype', ref.ctype);
  if (ref.body) {
    const scripts = urlsIn(ref.body).filter(u => /\.js(\?|$)/.test(u));
    console.log('script urls:', scripts.slice(0, 15));
    console.log('api hints in page:', apiHints(ref.body));
    // fetch the biggest same-origin app bundle and mine it for endpoints
    const appJs = scripts.map(u => u.startsWith('http') ? u : new URL(u, 'https://buswhere.com').toString())
      .find(u => /app|main|bundle|shuttle/i.test(u)) || (scripts[0] && new URL(scripts[0], 'https://buswhere.com').toString());
    if (appJs) {
      console.log('\n-- fetching app bundle:', appJs);
      const js = await hit(appJs);
      console.log('bundle status', js.status, 'len', (js.body || '').length);
      if (js.body) console.log('endpoint hints in bundle:', apiHints(js.body));
    }
  }

  // 2) find the USDA slug
  console.log('\n===== USDA slug candidates =====');
  const slugs = ['usda', 'USDA', 'usda_shuttle', 'usdashuttle', 'usda-shuttle', 'USDAShuttle', 'ars', 'gwcc', 'usda_gwcc'];
  const found = [];
  for (const s of slugs) {
    const r = await hit(`https://buswhere.com/${s}`);
    const ok = r.status === 200 && !/not found|404/i.test(r.body || '');
    console.log(`/${s}: HTTP ${r.status} finalUrl=${r.finalUrl} ${ok ? 'CANDIDATE' : ''}`);
    if (ok) found.push({ s, body: r.body });
  }

  // 3) for a found slug, list routes + data endpoints and test CORS
  for (const f of found.slice(0, 2)) {
    console.log(`\n===== /${f.s} details =====`);
    console.log('routes/links:', urlsIn(f.body).filter(u => /route|\/[a-z0-9_]+$/i.test(u)).slice(0, 20));
    console.log('api hints:', apiHints(f.body));
  }
}
main().catch(e => { console.error('FATAL', e); process.exit(1); });
