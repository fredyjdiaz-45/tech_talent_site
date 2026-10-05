// node --test domain-owner/
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseRdap, rdapBase } from './owner.mjs';

const card = (role, fn, org, email) => ({ roles: [role], vcardArray: ['vcard', [
  ['version', {}, 'text', '4.0'], ['fn', {}, 'text', fn], ['org', {}, 'text', org], ['email', {}, 'text', email]]] });

test('registrant org from registrar RDAP, registrar + date from registry', () => {
  const registrar = { entities: [card('registrant', 'Domain Admin', 'Acme Corp', 'dns@acme.com')] };
  const registry = { events: [{ eventAction: 'registration', eventDate: '1999-01-02T00:00:00Z' }],
    entities: [{ ...card('registrar', 'MarkMonitor Inc.', '', ''), entities: [card('abuse', 'Abuse', '', 'a@mm.com')] }] };
  assert.deepEqual(parseRdap(registrar, registry),
    { owner: 'Acme Corp', email: 'dns@acme.com', registrar: 'MarkMonitor Inc.', created: '1999-01-02' });
});

test('privacy-redacted registrant yields empty owner', () => {
  const doc = { entities: [card('registrant', 'REDACTED FOR PRIVACY', 'Privacy service provided by Withheld for Privacy ehf', '')] };
  assert.equal(parseRdap(doc).owner, '');
});

test('picks registry RDAP server by TLD', () => {
  const services = [[['com', 'net'], ['https://rdap.verisign.com/com/v1/']], [['gov'], ['https://rdap.cloudflareregistry.com/rdap/']]];
  assert.equal(rdapBase(services, 'oig.sba.gov'), 'https://rdap.cloudflareregistry.com/rdap/');
  assert.equal(rdapBase(services, 'chase.com'), 'https://rdap.verisign.com/com/v1/');
  assert.equal(rdapBase(services, 'novo.co'), undefined);
});
