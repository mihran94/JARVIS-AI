import test from 'node:test';
import assert from 'node:assert/strict';
import { BridgeClient, signCanonical } from '../js/bridge.js';
import { deviceRecord, deviceStorage } from '../js/device.js';

test('remembered browser signs the same protocol without retaining or exporting the raw secret', async () => {
  const secret = 'test-only-device-secret-0123456789abcdef';
  const record = await deviceRecord({ baseUrl: 'https://pc.test', keyId: 'test-phone', secret }, 'https://pc.test');
  assert.deepEqual(Object.keys(record).sort(), ['baseUrl', 'keyId', 'signingKey']);
  await assert.rejects(() => crypto.subtle.exportKey('raw', record.signingKey));
  const restored = structuredClone(record);
  assert.equal(await signCanonical('test request', restored.signingKey), await signCanonical('test request', secret));
  const client = new BridgeClient(restored);
  assert.equal(client.secret, undefined);
  assert.equal(client.keyId, 'test-phone');
});

test('a remembered key cannot be stored for another origin or an insecure page', async () => {
  const client = { baseUrl: 'https://pc.test', keyId: 'test-phone', secret: 'x'.repeat(40) };
  await assert.rejects(() => deviceRecord(client, 'https://other.test'), /own HTTPS/);
  await assert.rejects(() => deviceRecord({ ...client, baseUrl: 'http://pc.test' }, 'http://pc.test'), /own HTTPS/);
});

test('private browsing without device storage remains usable for the current page', async () => {
  const store = deviceStorage(null);
  assert.equal(await store.read(), null);
  await store.clear();
});
