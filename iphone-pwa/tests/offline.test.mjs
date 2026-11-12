// The outbox that keeps work while the PC cannot be reached.
import test from 'node:test';
import assert from 'node:assert/strict';

import { MAX_QUEUE_LENGTH, Outbox } from '../js/offline.js';

test('an item that succeeds is removed', async () => {
  const outbox = new Outbox();
  let ran = 0;
  outbox.push({ run: async () => { ran += 1; } });
  const result = await outbox.flush();
  assert.equal(ran, 1);
  assert.equal(result.sent, 1);
  assert.equal(outbox.length, 0);
});

test('an item that fails stays and waits longer', async () => {
  let clock = 1000;
  const outbox = new Outbox({ now: () => clock, baseBackoffMs: 2000 });
  outbox.push({ run: async () => { throw new Error('offline'); } });
  const first = await outbox.flush();
  assert.equal(first.failed, 1);
  assert.equal(outbox.length, 1);
  assert.equal(outbox.ready(clock).length, 0, 'the item waits before it is tried again');

  clock += 1999;
  assert.equal(outbox.ready(clock).length, 0);
  clock += 2;
  assert.equal(outbox.ready(clock).length, 1);
});

test('the wait grows with every attempt and is bounded', () => {
  const outbox = new Outbox({ baseBackoffMs: 1000, maxBackoffMs: 8000 });
  assert.equal(outbox.backoffFor(1), 1000);
  assert.equal(outbox.backoffFor(2), 2000);
  assert.equal(outbox.backoffFor(3), 4000);
  assert.equal(outbox.backoffFor(9), 8000);
});

test('the queue never grows past its limit', () => {
  const outbox = new Outbox({ maxLength: 3 });
  for (let index = 0; index < 6; index += 1) {
    outbox.push({ run: async () => {} });
  }
  assert.equal(outbox.length, 3);
});

test('an item without something to run is refused', () => {
  const outbox = new Outbox();
  assert.throws(() => outbox.push({}), /something to run/);
});

test('the queue can be emptied', async () => {
  const outbox = new Outbox();
  outbox.push({ run: async () => { throw new Error('no'); } });
  await outbox.flush();
  assert.equal(outbox.length, 1);
  outbox.clear();
  assert.equal(outbox.length, 0);
});

test('the limit is the agreed one', () => {
  assert.equal(MAX_QUEUE_LENGTH, 20);
});
