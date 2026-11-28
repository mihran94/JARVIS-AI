// The outbox that keeps work while the PC cannot be reached.
//
// The queue holds plain descriptors, not functions, so it can be written down
// and read back after a reload. The tests use a fake store instead of
// IndexedDB, because node has no IndexedDB and the page has no build step.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import {
  BASE_BACKOFF_MS,
  DEDUPE_WINDOW_MS,
  KINDS,
  MAX_BACKOFF_MS,
  MAX_QUEUE_LENGTH,
  Outbox,
  canonicalJson,
  createIndexedDbStore,
  idempotencyKey,
} from '../js/offline.js';

const here = dirname(fileURLToPath(import.meta.url));

/** A store that keeps the queue in memory, for the tests. */
class FakeStore {
  constructor(saved = []) {
    this.saved = saved.map((item) => ({ ...item }));
    this.writes = 0;
    this.reads = 0;
  }

  async load() {
    this.reads += 1;
    return this.saved.map((item) => ({ ...item }));
  }

  async save(items) {
    this.writes += 1;
    this.saved = items.map((item) => ({ ...item }));
  }
}

/** A store that always fails, for the tests. */
class BrokenStore {
  async load() {
    throw new Error('the disk is full');
  }

  async save() {
    throw new Error('the disk is full');
  }
}

test('an item that succeeds is sent and removed', async () => {
  const outbox = new Outbox();
  const sent = [];
  await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello', consent: false } });
  const result = await outbox.flush(async (item) => { sent.push(item); });
  assert.equal(sent.length, 1);
  assert.equal(sent[0].kind, KINDS.CHAT);
  assert.equal(sent[0].payload.message, 'hello');
  assert.equal(result.sent, 1);
  assert.equal(result.failed, 0);
  assert.equal(result.remaining, 0);
  assert.equal(outbox.length, 0);
});

test('an item that fails stays and waits longer', async () => {
  let clock = 1000;
  const outbox = new Outbox({ now: () => clock, baseBackoffMs: 2000 });
  await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello' } });
  const first = await outbox.flush(async () => { throw new Error('offline'); });
  assert.equal(first.failed, 1);
  assert.equal(first.sent, 0);
  assert.equal(first.remaining, 1);
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

test('the wait of a failing item grows and stays bounded', async () => {
  let clock = 1000;
  const outbox = new Outbox({ now: () => clock, baseBackoffMs: 1000, maxBackoffMs: 8000 });
  await outbox.push({ kind: KINDS.TASK, payload: { title: 'backup' } });
  const waits = [];
  for (let attempt = 0; attempt < 6; attempt += 1) {
    await outbox.flush(async () => { throw new Error('offline'); });
    waits.push(outbox.items[0].nextAttemptAt - clock);
    outbox.items[0].nextAttemptAt = 0;
  }
  assert.deepEqual(waits.slice(0, 4), [1000, 2000, 4000, 8000]);
  assert.equal(waits[4], 8000, 'the wait never grows past the bound');
  assert.equal(waits[5], 8000);
});

test('the queue never grows past its limit', async () => {
  const outbox = new Outbox({ maxLength: 3 });
  for (let index = 0; index < 6; index += 1) {
    await outbox.push({ kind: KINDS.CHAT, payload: { message: `question ${index}` } });
  }
  assert.equal(outbox.length, 3);
  assert.equal(outbox.dropped, 3, 'the page can say that three items were lost');
});

test('an item without a kind is refused', async () => {
  const outbox = new Outbox();
  await assert.rejects(() => outbox.push({ payload: { message: 'hello' } }), /needs a kind/);
  await assert.rejects(() => outbox.push({ kind: '  ' }), /needs a kind/);
});

test('an item with something that cannot be written down is refused', async () => {
  const outbox = new Outbox();
  await assert.rejects(() => outbox.push({
    kind: KINDS.CHAT,
    payload: { run: () => {} },
  }), /plain data/);
});

test('the queue can be emptied', async () => {
  const outbox = new Outbox();
  await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello' } });
  await outbox.flush(async () => { throw new Error('no'); });
  assert.equal(outbox.length, 1);
  await outbox.clear();
  assert.equal(outbox.length, 0);
});

test('the limit is the agreed one', () => {
  assert.equal(MAX_QUEUE_LENGTH, 20);
  assert.equal(BASE_BACKOFF_MS, 2000);
  assert.equal(MAX_BACKOFF_MS, 60000);
});

test('a queued item is plain data and can be written down', async () => {
  const outbox = new Outbox();
  await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello', consent: true } });
  const item = outbox.items[0];
  assert.deepEqual(Object.keys(item).sort(),
    ['attempts', 'createdAt', 'id', 'kind', 'nextAttemptAt', 'payload']);
  assert.equal(typeof item.payload.run, 'undefined');
  const written = JSON.parse(JSON.stringify(item));
  assert.deepEqual(written.payload, { message: 'hello', consent: true });
});

test('the same command twice is queued once and sent once', async () => {
  const outbox = new Outbox();
  const first = await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello', consent: false } });
  const second = await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello', consent: false } });
  assert.equal(first.duplicate, false);
  assert.equal(second.duplicate, true, 'the second push is not a second item');
  assert.equal(outbox.length, 1);
  assert.equal(second.item.id, first.item.id);

  let sent = 0;
  const result = await outbox.flush(async () => { sent += 1; });
  assert.equal(sent, 1, 'the work is sent once');
  assert.equal(result.sent, 1);
});

test('the key of a command does not depend on the order of its fields', () => {
  const one = idempotencyKey(KINDS.CHAT, { message: 'hello', consent: false });
  const other = idempotencyKey(KINDS.CHAT, { consent: false, message: 'hello' });
  assert.equal(one, other);
  assert.notEqual(one, idempotencyKey(KINDS.TASK, { message: 'hello', consent: false }));
  assert.notEqual(one, idempotencyKey(KINDS.CHAT, { message: 'goodbye', consent: false }));
  assert.equal(canonicalJson({ b: 1, a: 2 }), '{"a":2,"b":1}');
});

test('a command that was sent is not queued again inside the window', async () => {
  let clock = 1000;
  const outbox = new Outbox({ now: () => clock, dedupeWindowMs: DEDUPE_WINDOW_MS });
  await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello' } });
  await outbox.flush(async () => {});
  assert.equal(outbox.length, 0);

  const again = await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello' } });
  assert.equal(again.duplicate, true);
  assert.equal(outbox.length, 0, 'the work is not queued a second time');

  clock += DEDUPE_WINDOW_MS + 1;
  const later = await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello' } });
  assert.equal(later.duplicate, false, 'after the window the same question is a new one');
  assert.equal(outbox.length, 1);
});

test('work that was done by hand is not sent a second time', async () => {
  const outbox = new Outbox();
  const task = { kind: KINDS.TASK, payload: { title: 'backup', payload: '' } };
  await outbox.push(task);
  assert.equal(outbox.length, 1);
  assert.equal(await outbox.discard(KINDS.TASK, task.payload), true);
  assert.equal(outbox.length, 0);

  const result = await outbox.flush(async () => { throw new Error('should not run'); });
  assert.equal(result.sent, 0);
  assert.equal(result.remaining, 0);
});

test('the queue is written down and read back', async () => {
  const store = new FakeStore();
  const outbox = new Outbox({ store });
  await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello', consent: false } });
  await outbox.push({ kind: KINDS.TASK, payload: { title: 'backup' } });
  assert.equal(store.saved.length, 2);
  assert.deepEqual(store.saved[0].payload, { message: 'hello', consent: false });

  const other = new Outbox({ store });
  assert.equal(other.length, 0, 'a new page starts empty');
  const waiting = await other.restore();
  assert.equal(waiting, 2);
  assert.equal(other.length, 2);
  assert.equal(other.items[0].kind, KINDS.CHAT);
  assert.equal(other.items[1].kind, KINDS.TASK);
  assert.deepEqual(other.items[1].payload, { title: 'backup' });
});

test('the work survives a reload and goes out afterwards', async () => {
  let clock = 1000;
  const store = new FakeStore();
  const first = new Outbox({ store, now: () => clock });
  await first.push({ kind: KINDS.CHAT, payload: { message: 'hello', consent: false } });
  await first.flush(async () => { throw new Error('the PC is not there'); });
  assert.equal(first.length, 1, 'the work is still waiting');

  // The page is reloaded: a new outbox reads the queue back from the phone.
  clock += 10000;
  const second = new Outbox({ store, now: () => clock });
  await second.restore();
  assert.equal(second.length, 1, 'the work is still there after the reload');

  const sent = [];
  const result = await second.flush(async (item) => { sent.push(item.payload.message); });
  assert.deepEqual(sent, ['hello']);
  assert.equal(result.sent, 1);
  assert.equal(result.remaining, 0);
  assert.equal(second.length, 0);
  assert.equal(store.saved.length, 0, 'the queue on the phone is empty again');
});

test('the queue keeps the newest attempt state when it is read back', async () => {
  const store = new FakeStore();
  const first = new Outbox({ store });
  await first.push({ kind: KINDS.CHAT, payload: { message: 'hello' } });
  await first.flush(async () => { throw new Error('offline'); });
  assert.equal(first.items[0].attempts, 1);

  const second = new Outbox({ store });
  await second.restore();
  assert.equal(second.items[0].attempts, 1, 'the attempt is not forgotten');
  assert.equal(second.items[0].nextAttemptAt, first.items[0].nextAttemptAt);
});

test('a queue that cannot be saved says so', async () => {
  const outbox = new Outbox({ store: new BrokenStore() });
  const result = await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello' } });
  assert.equal(result.persisted, false);
  assert.match(outbox.storageError, /the disk is full/);
  assert.equal(outbox.length, 1, 'the work is still kept in the page');
});

test('a queue without a store never touches the storage', async () => {
  const outbox = new Outbox();
  assert.equal(outbox.store, null);
  await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello' } });
  assert.equal(outbox.length, 1);
  assert.equal(await outbox.restore(), 0, 'there is nothing to read back');
  assert.equal(outbox.storageError, '');
});

test('no store is made when the browser has no IndexedDB', () => {
  assert.equal(createIndexedDbStore({ indexedDb: null }), null);
});

test('the flush needs an executor', async () => {
  const outbox = new Outbox();
  await outbox.push({ kind: KINDS.CHAT, payload: { message: 'hello' } });
  await assert.rejects(() => outbox.flush(), /needs an executor/);
});

test('the counters say what happened', async () => {
  const outbox = new Outbox();
  await outbox.push({ kind: KINDS.CHAT, payload: { message: 'one' } });
  await outbox.push({ kind: KINDS.CHAT, payload: { message: 'two' } });
  await outbox.push({ kind: KINDS.CHAT, payload: { message: 'three' } });
  const result = await outbox.flush(async (item) => {
    if (item.payload.message === 'two') {
      throw new Error('offline');
    }
  });
  assert.equal(result.sent, 2);
  assert.equal(result.failed, 1);
  assert.equal(result.remaining, 1);
  assert.equal(outbox.length, 1);
});

test('the page does not promise a delivery in the background', async () => {
  const page = await readFile(join(here, '..', 'app.js'), 'utf-8');
  const html = await readFile(join(here, '..', 'index.html'), 'utf-8');
  for (const [name, text] of [['app.js', page], ['index.html', html]]) {
    assert.ok(!text.includes('when the connection returns'),
      `${name} still promises a delivery that iOS cannot make`);
  }
  assert.ok(page.includes('goes out when this app is open'), 'app.js does not say what really happens');
  assert.ok(html.includes('sent when the app is open'), 'index.html does not say what really happens');
});

/** A part of a page, just enough for the wiring to run. */
function fakeElement(id) {
  const listeners = {};
  return {
    id,
    dataset: {},
    removeAttribute() {},
    value: '',
    checked: false,
    textContent: '',
    className: '',
    hidden: false,
    scrollHeight: 0,
    childElementCount: 0,
    children: [],
    addEventListener(type, handler) {
      (listeners[type] = listeners[type] || []).push(handler);
    },
    /** Let the test press a button. */
    press() {
      for (const handler of listeners.click || []) {
        handler({ preventDefault() {}, target: this });
      }
    },
    appendChild(child) {
      this.children.push(child);
      this.childElementCount = this.children.length;
    },
    append(...children) { this.children.push(...children); },
    prepend(child) { this.children.unshift(child); },
    setAttribute() {},
    scrollTo() {},
  };
}

/** Let the queued work settle. */
function settle() {
  return new Promise((resolve) => setTimeout(resolve, 10));
}

/** Wait until the page says what the test expects. */
async function waitFor(check, description, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (check()) {
      return;
    }
    await settle();
  }
  assert.fail(`the page never ${description}`);
}

test('the page keeps the work that cannot be sent and sends it later', async () => {
  const elements = new Map();
  const windowListeners = {};
  // The fake page stays in place after the test: the page is still finishing
  // its work, and it must not find a document that has gone.
  globalThis.document = {
    readyState: 'complete',
    hidden: false,
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, fakeElement(id));
      }
      return elements.get(id);
    },
    createElement(tag) {
      if (tag === 'canvas') {
        return { getContext: () => ({ drawImage() {} }),
          toDataURL: () => 'data:image/jpeg;base64,frame' };
      }
      return fakeElement(tag);
    },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener() {},
  };
  globalThis.window = {
    addEventListener(type, handler) {
      (windowListeners[type] = windowListeners[type] || []).push(handler);
    },
  };
  // The heartbeat of the page is not wanted in a test.
  globalThis.setInterval = () => 0;
  globalThis.clearInterval = () => {};

  const requests = [];
  let networkDown = true;
  globalThis.fetch = async (url, options) => {
    requests.push({ url, method: options.method, down: networkDown, body: options.body });
    if (networkDown) {
      throw new Error('the network is down');
    }
    return {
      ok: true,
      status: 200,
      async text() {
        if (url.endsWith('/api/chat')) {
          return JSON.stringify({ text: 'the answer', provider: 'the PC' });
        }
        return JSON.stringify({});
      },
    };
  };

  const element = (id) => globalThis.document.getElementById(id);
  element('url').value = 'https://pc.example.lan';
  element('key').value = 'iphone-1';
  element('secret').value = 'x'.repeat(40);
  element('message').value = 'hello there';
  element('taskTitle').value = 'nightly backup';

  await import('../app.js');
  await settle();

  element('connect').press();
  await waitFor(() => /could not be reached/.test(element('banner').textContent),
    'said that the PC is out of reach');

  // The PC cannot be reached, so the message is kept.
  element('send').press();
  await waitFor(() => /^1 item\(s\) are waiting/.test(element('outboxStatus').textContent),
    'kept the message');
  assert.match(element('banner').textContent, /kept on this phone/);

  // The same message again is the same work, so it is not queued twice.
  element('send').press();
  await waitFor(() => /already waiting/.test(element('banner').textContent),
    'said that the work was already waiting');
  assert.match(element('outboxStatus').textContent, /^1 item\(s\) are waiting/);

  // A task that cannot be sent is kept as well.
  element('submitTask').press();
  await waitFor(() => /^2 item\(s\) are waiting/.test(element('outboxStatus').textContent),
    'kept the task');

  // The PC comes back and the app is told.
  networkDown = false;
  for (const handler of windowListeners.online || []) {
    handler({});
  }
  await waitFor(() => /sent to the PC/.test(element('banner').textContent),
    'sent the waiting work');
  assert.equal(element('outboxStatus').textContent, '');
  const posted = requests.filter((request) => request.method === 'POST' && !request.down);
  assert.equal(posted.length, 2, 'the chat and the task go out once each');
  assert.ok(posted.some((request) => request.url.endsWith('/api/chat')));
  assert.ok(posted.some((request) => request.url.endsWith('/api/jobs')));
  let stopped = false;
  const stream = { getTracks: () => [{ stop() { stopped = true; } }] };
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    configurable: true, value: { getUserMedia: async () => stream },
  });
  const view = element('liveCameraView');
  view.videoWidth = 400;
  view.videoHeight = 300;
  view.play = async () => {};
  element('consent').checked = true;
  element('phoneCamera').press();
  await waitFor(() => view.srcObject === stream, 'started the camera');
  element('message').value = 'Look at this';
  element('send').press();
  await waitFor(() => requests.some((request) => request.body?.includes('"images":["frame"]')),
    'sent the frame with the question');
  globalThis.window.location = { hash: '' };
  element('message').value = '';
  element('lookNow').press();
  await waitFor(() => requests.some((request) => request.body?.includes('இது என்ன?')),
    'asked what the camera sees');
  assert.equal(window.location.hash, 'chatPanel');
  element('checkDisk').press();
  await waitFor(() => requests.some((request) => request.url.endsWith('/api/jobs')
    && request.body?.includes('check_disk_space')), 'sent the command as a desktop job');
  element('phoneCamera').press();
  assert.equal(stopped, true);
  assert.equal(view.srcObject, null);
  const storage = new Map();
  globalThis.localStorage = {
    setItem: (key, value) => storage.set(key, value),
    getItem: (key) => storage.get(key),
    removeItem: (key) => storage.delete(key),
  };
  globalThis.location = new URL(element('url').value);
  globalThis.history = { replaceState() { location.hash = ''; } };
  element('siriLink').select = () => {};
  element('enableSiriWake').press();
  await waitFor(() => element('siriLink').value, 'created a Siri wake link');
  assert.equal(element('siriLink').value, 'https://pc.example.lan/#wake');
  assert.equal(storage.size, 1);
  assert.ok(![...storage.values()][0].includes(element('secret').value));
  location.hash = 'wake';
  for (const handler of windowListeners.hashchange) await handler();
  assert.equal(requests.filter(r => r.url.endsWith('/api/wake')).length, 1);
  assert.equal(location.hash, '');
  // Let the page finish the work it started, so nothing is left running when
  // the test ends.
  await settle();
  await settle();
});
