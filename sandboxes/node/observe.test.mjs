// Public response-shape checks and observation collection, never the hidden oracle.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';

const variant = process.env.LABPROOF_VARIANT;
if (!['alpha', 'beta', 'gamma', 'delta'].includes(variant)) throw new Error('Invalid variant');
const root = `/fixture/${variant}`;
const raw = await readFile(`${root}/inputs.json`);
assert.ok(raw.length <= 4096);
const inputs = JSON.parse(raw.toString('utf8'));
assert.ok(Array.isArray(inputs) && inputs.length >= 1 && inputs.length <= 8);
const ids = new Set();
for (const row of inputs) {
  assert.ok(row && typeof row === 'object' && !Array.isArray(row));
  assert.deepEqual(Object.keys(row).sort(), ['actor', 'id', 'record_id']);
  assert.ok(Object.values(row).every(v => typeof v === 'string'));
  assert.match(row.id, /^case-0[1-8]$/);
  assert.ok(!ids.has(row.id)); ids.add(row.id);
  assert.ok(['alice', 'bob', 'guest'].includes(row.actor));
  assert.ok(['record-alice', 'record-bob', 'record-missing'].includes(row.record_id));
}
// Native Node type stripping is not static typechecking or compilation evidence.
const {readRecord} = await import(pathToFileURL(`${root}/authz.ts`).href);
for (const row of inputs) {
  test(row.id, t => {
    const response = readRecord(row.actor, row.record_id);
    assert.deepEqual(Object.keys(response).sort(), ['body', 'status']);
    assert.ok(Number.isInteger(response.status) && response.status >= 100 && response.status <= 599);
    assert.ok(response.body && typeof response.body === 'object' && !Array.isArray(response.body));
    const pairs = Object.entries(response.body);
    assert.ok(pairs.length <= 4 && pairs.every(([k,v]) => typeof v === 'string' && k.length <= 80 && v.length <= 128));
    t.diagnostic(JSON.stringify({case_id: row.id, response}));
  });
}
