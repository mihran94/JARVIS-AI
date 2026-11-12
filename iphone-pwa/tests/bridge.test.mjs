// The bridge client must sign exactly the way the desktop signs.
//
// The vector below is the one that is pinned in the desktop test suite and
// in the Android client. If this file and remote/protocol.py ever disagree,
// this test fails.
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  BridgeClient, BridgeError, canonicalString, checkBridgeUrl, makeNonce, sha256Hex,
  signCanonical, signRequest,
} from '../js/bridge.js';

const SECRET = 'shared-secret-for-tests-0123456789abcdef';

test('the pinned vector from the desktop is reproduced', async () => {
  const signature = await signRequest({
    method: 'GET',
    path: '/api/status',
    timestamp: '1700000000000',
    nonce: 'nonce-123',
    body: '',
    secret: 'test-secret',
  });
  assert.equal(signature, '5a0eff83c8875fc160be921c708461920dfa3f9775821784555822eb38d32a3d');
});

test('the canonical string has the agreed field order', () => {
  assert.equal(canonicalString('get', '/api/status', '1700000000000', 'n', 'abc'),
    'GET\n/api/status\n1700000000000\nn\nabc');
});

test('the digest of an empty body is the well known value', async () => {
  assert.equal(await sha256Hex(''),
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
});

test('a nonce is 32 hex characters of fresh random', () => {
  const nonce = makeNonce(() => new Uint8Array(16).fill(0xab));
  assert.equal(nonce, 'ab'.repeat(16));
});

test('a different body gives a different signature', async () => {
  const one = await signCanonical('GET\n/x\n1\nn\nabc', SECRET);
  const other = await signCanonical('GET\n/x\n1\nn\ndef', SECRET);
  assert.notEqual(one, other);
});

test('only https is accepted', () => {
  assert.throws(() => checkBridgeUrl('http://pc.example.lan'), /HTTPS/);
  assert.throws(() => checkBridgeUrl('https://user:pass@pc.example.lan'), /user name/);
  assert.throws(() => checkBridgeUrl('not a url'), /full bridge URL/);
  assert.equal(checkBridgeUrl('https://pc.example.lan').protocol, 'https:');
});

test('plain http is allowed for loopback only when it is asked for', () => {
  assert.throws(() => checkBridgeUrl('http://127.0.0.1:8765'), /HTTPS/);
  const parsed = checkBridgeUrl('http://127.0.0.1:8765', { allowLoopbackHttp: true });
  assert.equal(parsed.hostname, '127.0.0.1');
  assert.throws(() => checkBridgeUrl('http://pc.example.lan', { allowLoopbackHttp: true }), /HTTPS/);
});

test('a client needs a key id and a long enough secret', () => {
  assert.throws(() => new BridgeClient({ baseUrl: 'https://pc.example.lan', keyId: '', secret: SECRET }),
    /key id/);
  assert.throws(() => new BridgeClient({ baseUrl: 'https://pc.example.lan', keyId: 'k', secret: 'short' }),
    /at least 32 characters/);
});

// ---------------------------------------------------------------- requests

function fakeResponse(payload, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    text: async () => (typeof payload === 'string' ? payload : JSON.stringify(payload)),
  };
}

function makeClient(overrides = {}) {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return fakeResponse(overrides.payload ?? { ok: true }, overrides);
  };
  const client = new BridgeClient({
    baseUrl: 'https://pc.example.lan',
    keyId: 'iphone-test',
    secret: SECRET,
    fetchImpl,
    now: () => 1700000000000,
    randomBytes: () => new Uint8Array(16).fill(0xab),
  });
  return { client, calls };
}

test('every request carries the four protocol headers', async () => {
  const { client, calls } = makeClient();
  await client.status();
  const headers = calls[0].options.headers;
  assert.equal(headers['X-Jarvis-Key-Id'], 'iphone-test');
  assert.equal(headers['X-Jarvis-Timestamp'], '1700000000000');
  assert.equal(headers['X-Jarvis-Nonce'], 'ab'.repeat(16));
  assert.match(headers['X-Jarvis-Signature'], /^[0-9a-f]{64}$/);
});

test('a request never sends cookies and never follows a redirect', async () => {
  const { client, calls } = makeClient();
  await client.status();
  assert.equal(calls[0].options.credentials, 'omit');
  assert.equal(calls[0].options.redirect, 'error');
  assert.equal(calls[0].options.cache, 'no-store');
});

test('the secret never appears in the request', async () => {
  const { client, calls } = makeClient();
  await client.chat('hello', { consent: true });
  const everything = JSON.stringify(calls[0]);
  assert.equal(everything.includes(SECRET), false);
});

test('a chat request sends the message and the consent flag', async () => {
  const { client, calls } = makeClient({ payload: { text: 'hi' } });
  await client.chat('hello', { consent: true });
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(JSON.parse(calls[0].options.body).message, 'hello');
  assert.equal(JSON.parse(calls[0].options.body).consent, true);
});

test('a task is sent with the approval flag', async () => {
  const { client, calls } = makeClient({ payload: { id: '1', state: 'QUEUED' } });
  await client.submitJob({ title: 'Nightly backup' });
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.title, 'Nightly backup');
  assert.equal(body.requireApproval, true);
});

test('a task needs a title', async () => {
  const { client } = makeClient();
  await assert.rejects(() => client.submitJob({ title: '  ' }), /title/);
});

test('the job list is always an array', async () => {
  const { client } = makeClient({ payload: { jobs: [{ id: '1' }] } });
  assert.deepEqual(await client.jobs(), [{ id: '1' }]);
  const empty = makeClient({ payload: {} });
  assert.deepEqual(await empty.client.jobs(), []);
});

test('a path is escaped so a job id cannot reach another endpoint', async () => {
  const { client, calls } = makeClient();
  await client.job('a/../../etc');
  assert.ok(calls[0].url.endsWith('/api/jobs/a%2F..%2F..%2Fetc'));
});

test('a failure carries the message of the desktop', async () => {
  const { client } = makeClient({ payload: { error: 'That is not allowed.' }, ok: false, status: 403 });
  await assert.rejects(() => client.status(), (error) => {
    assert.ok(error instanceof BridgeError);
    assert.equal(error.status, 403);
    assert.equal(error.message, 'That is not allowed.');
    return true;
  });
});

test('an unreachable PC gives a clear message', async () => {
  const client = new BridgeClient({
    baseUrl: 'https://pc.example.lan',
    keyId: 'iphone-test',
    secret: SECRET,
    fetchImpl: async () => { throw new Error('network down'); },
  });
  await assert.rejects(() => client.status(), /could not be reached/);
});

test('a path that is not a path is refused', async () => {
  const { client } = makeClient();
  await assert.rejects(() => client.request('GET', 'api/status'), /must start with/);
});
