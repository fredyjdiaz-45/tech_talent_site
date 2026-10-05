#!/usr/bin/env node
// Find who owns each domain. Usage: node owner.mjs domains.txt > owners.csv  (or pipe domains on stdin)
// Sources, no API keys: RDAP (the JSON successor to WHOIS) for registrant/registrar,
// then the TLS certificate's Organization field (OV/EV certs name the company even when WHOIS is redacted).
import { readFileSync } from 'node:fs';
import tls from 'node:tls';
import { fileURLToPath } from 'node:url';

const REDACTED = /redact|privacy|private|proxy|withheld|not disclosed|data protected|contact privacy/i;

// RDAP vCard -> {name, org, email}
const vcard = (e) => Object.fromEntries((e.vcardArray?.[1] ?? [])
  .filter(([k]) => ['fn', 'org', 'email'].includes(k))
  .map(([k, , , v]) => [k === 'fn' ? 'name' : k, [v].flat().join(' ').trim()]));

// Walk nested entities, return the first one holding `role`.
export const findRole = (entities = [], role) => {
  for (const e of entities) {
    if (e.roles?.includes(role)) return e;
    const hit = findRole(e.entities, role);
    if (hit) return hit;
  }
};

export const clean = (s) => (s && !REDACTED.test(s) ? s : '');

export function parseRdap(...docs) {
  const reg = docs.map((d) => findRole(d.entities, 'registrant')).find(Boolean);
  const r = reg ? vcard(reg) : {};
  const registrar = docs.map((d) => findRole(d.entities, 'registrar')).find(Boolean);
  const created = docs.flatMap((d) => d.events ?? []).find((e) => e.eventAction === 'registration')?.eventDate ?? '';
  return {
    owner: clean(r.org) || clean(r.name),
    email: clean(r.email),
    registrar: registrar ? vcard(registrar).name ?? '' : '',
    created: created.slice(0, 10),
  };
}

const getJson = async (url) => {
  const res = await fetch(url, { headers: { accept: 'application/rdap+json' }, signal: AbortSignal.timeout(15000) });
  if (!res.ok) throw new Error(`RDAP ${res.status}`);
  return res.json();
};

async function rdap(domain) {
  // rdap.org redirects to the right registry. Thin registries (.com/.net) only know the registrar,
  // so follow the "related" link to the registrar's RDAP for registrant details.
  const registry = await getJson(`https://rdap.org/domain/${domain}`);
  const link = registry.links?.find((l) => l.rel === 'related' && /rdap/.test(l.type ?? l.href));
  const registrar = link ? await getJson(link.href).catch(() => null) : null;
  return parseRdap(...[registrar, registry].filter(Boolean));
}

const certOrg = (domain) => new Promise((resolve) => {
  const s = tls.connect({ host: domain, port: 443, servername: domain, timeout: 10000 }, () => {
    resolve(s.getPeerCertificate().subject?.O ?? '');
    s.end();
  });
  s.on('error', () => resolve(''));
  s.on('timeout', () => { s.destroy(); resolve(''); });
});

async function lookup(domain) {
  const [r, org] = await Promise.all([rdap(domain).catch((e) => ({ error: e.message })), certOrg(domain)]);
  const owner = r.owner || org;
  return { domain, owner, source: r.owner ? 'rdap' : org ? 'tls-cert' : '', cert_org: org,
    registrant_email: r.email ?? '', registrar: r.registrar ?? '', created: r.created ?? '', error: r.error ?? '' };
}

const csv = (v) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const input = readFileSync(process.argv[2] ?? 0, 'utf8');
  const domains = [...new Set(input.split(/[\s,]+/)
    .map((d) => d.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, '').replace(/^www\./, ''))
    .filter((d) => /^[a-z0-9.-]+\.[a-z]{2,}$/.test(d)))];
  const cols = ['domain', 'owner', 'source', 'cert_org', 'registrant_email', 'registrar', 'created', 'error'];
  console.log(cols.join(','));
  // ponytail: sequential with a 1s gap to stay under registry rate limits; fine for ~100/month, parallelize with a small pool if lists grow to thousands.
  for (const d of domains) {
    const row = await lookup(d);
    console.log(cols.map((c) => csv(row[c])).join(','));
    await new Promise((r) => setTimeout(r, 1000));
  }
}
