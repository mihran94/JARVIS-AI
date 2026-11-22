// The outbox for a phone that is out of reach.
//
// When the bridge cannot be reached, the work the person asked for is kept
// here as a plain descriptor: a kind, a payload and a little bookkeeping.
// There is no function and no closure in the queue, so the whole thing can be
// written to IndexedDB and read back after a reload. The page hands the
// executor over when it flushes, so nothing that cannot be written down ever
// enters the queue.
//
// iOS Safari does not implement Background Sync, so nothing here runs while
// the app is closed. The queue goes out when the app is in front: on the
// `online` event, when the app starts, when it comes back to the front, and
// every few seconds while the page is open.

/** How many items the outbox keeps. */
export const MAX_QUEUE_LENGTH = 20;

/** The first retry waits this many milliseconds. */
export const BASE_BACKOFF_MS = 2000;

/** The retries never wait longer than this. */
export const MAX_BACKOFF_MS = 60000;

/**
 * How long an item that was sent still blocks an equal one.
 *
 * The window is short on purpose: it stops a button that is pressed twice
 * from sending the same command twice, and it does not stop the same
 * question being asked again later.
 */
export const DEDUPE_WINDOW_MS = 5 * 60 * 1000;

/** The kinds of work the outbox knows. The page decides what each one means. */
export const KINDS = {
  CHAT: 'chat',
  TASK: 'task',
  NOTIFICATION_ACK: 'notification-ack',
};

/** The name of the IndexedDB database that holds the queue. */
export const DATABASE_NAME = 'jarvis-iphone-outbox';

/** The version of that database. */
export const DATABASE_VERSION = 1;

/** The object store inside the database. */
export const STORE_NAME = 'outbox';

// ------------------------------------------------------------------ helpers

/** The message of a failure, whatever it is. */
function messageOf(error) {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Whether a value is plain data that can be written to storage.
 *
 * A function, a symbol or a Date is refused: it would not survive the trip
 * through IndexedDB, and a queue that loses a command silently is worse than
 * no queue at all.
 */
function isPlainData(value, depth = 0) {
  if (depth > 12) {
    return false;
  }
  if (value === null) {
    return true;
  }
  const type = typeof value;
  if (type === 'string' || type === 'boolean' || type === 'undefined') {
    return true;
  }
  if (type === 'number') {
    return Number.isFinite(value);
  }
  if (Array.isArray(value)) {
    return value.every((entry) => isPlainData(entry, depth + 1));
  }
  if (type === 'object') {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      return false;
    }
    return Object.values(value).every((entry) => isPlainData(entry, depth + 1));
  }
  return false;
}

/** A copy of plain data that no longer shares anything with the original. */
function cloneData(value) {
  if (typeof structuredClone === 'function') {
    try {
      return structuredClone(value);
    } catch (error) {
      // Fall through to the JSON copy below.
    }
  }
  return JSON.parse(JSON.stringify(value === undefined ? null : value));
}

/**
 * The same data written the same way every time.
 *
 * The keys are sorted, so two payloads that hold the same values in a
 * different order produce the same text and therefore the same key.
 */
export function canonicalJson(value) {
  if (value === null || typeof value !== 'object') {
    const text = JSON.stringify(value);
    return text === undefined ? 'null' : text;
  }
  if (Array.isArray(value)) {
    return `[${value.map((entry) => canonicalJson(entry)).join(',')}]`;
  }
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
}

/** One round of the 32 bit FNV-1a hash. */
function fnv1a(text, seed) {
  let hash = seed >>> 0;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

/**
 * A stable hash of a string, as lowercase hex.
 *
 * The same text always gives the same hash, in this browser and in the next
 * one, which is what makes the deduplication work after a reload.
 */
export function hashText(text) {
  const first = fnv1a(text, 0x811c9dc5);
  const second = fnv1a(text, 0x9e3779b9);
  const third = fnv1a(`${text.length}:${text}`, 0x85ebca6b);
  return [first, second, third].map((value) => value.toString(16).padStart(8, '0')).join('');
}

/**
 * The key that says two pieces of work are the same work.
 *
 * It is built from the kind and the payload only, so it survives a reload
 * and it does not depend on the clock or on how many items are waiting.
 */
export function idempotencyKey(kind, payload) {
  return `${kind}:${hashText(canonicalJson(payload === undefined ? {} : payload))}`;
}

/** Read the kind and the payload out of a descriptor. */
function readDescriptor(descriptor) {
  if (!descriptor || typeof descriptor !== 'object') {
    throw new Error('An outbox item needs a kind and a payload.');
  }
  const kind = typeof descriptor.kind === 'string' ? descriptor.kind.trim() : '';
  if (!kind) {
    throw new Error('An outbox item needs a kind.');
  }
  const payload = descriptor.payload === undefined ? {} : descriptor.payload;
  if (!isPlainData(payload)) {
    throw new Error('An outbox payload has to be plain data.');
  }
  return { kind, payload: cloneData(payload) };
}

/** Read one item that came back from the store, or null when it is unusable. */
function readStoredItem(raw) {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const kind = typeof raw.kind === 'string' ? raw.kind.trim() : '';
  if (!kind) {
    return null;
  }
  const payload = raw.payload === undefined ? {} : raw.payload;
  if (!isPlainData(payload)) {
    return null;
  }
  const copied = cloneData(payload);
  const createdAt = Number.isFinite(raw.createdAt) ? raw.createdAt : 0;
  const attempts = Number.isFinite(raw.attempts) && raw.attempts > 0 ? Math.floor(raw.attempts) : 0;
  const nextAttemptAt = Number.isFinite(raw.nextAttemptAt) ? raw.nextAttemptAt : createdAt;
  return {
    id: idempotencyKey(kind, copied),
    kind,
    payload: copied,
    createdAt,
    attempts,
    nextAttemptAt,
  };
}

/** A copy of one item, so the store never holds a live reference. */
function cloneItem(item) {
  return {
    id: item.id,
    kind: item.kind,
    payload: cloneData(item.payload),
    createdAt: item.createdAt,
    attempts: item.attempts,
    nextAttemptAt: item.nextAttemptAt,
  };
}

// -------------------------------------------------------------------- store

/**
 * The queue in IndexedDB.
 *
 * The store is opened the first time it is used, never before, so a browser
 * without IndexedDB costs nothing. It keeps plain descriptors only.
 */
export class IndexedDbStore {
  constructor({
    databaseName = DATABASE_NAME,
    databaseVersion = DATABASE_VERSION,
    storeName = STORE_NAME,
    indexedDb = null,
  } = {}) {
    this.databaseName = databaseName;
    this.databaseVersion = databaseVersion;
    this.storeName = storeName;
    this.indexedDb = indexedDb !== null
      ? indexedDb
      : (typeof globalThis !== 'undefined' ? globalThis.indexedDB || null : null);
    this.database = null;
  }

  /** Open the database, once. */
  async open() {
    if (this.database) {
      return this.database;
    }
    if (!this.indexedDb) {
      throw new Error('This browser has no IndexedDB, so the queue cannot be saved.');
    }
    this.database = await new Promise((resolve, reject) => {
      let request;
      try {
        request = this.indexedDb.open(this.databaseName, this.databaseVersion);
      } catch (error) {
        reject(error);
        return;
      }
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains(this.storeName)) {
          database.createObjectStore(this.storeName, { keyPath: 'id' });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('The outbox database could not be opened.'));
      request.onblocked = () => reject(new Error('The outbox database is held by another tab.'));
    });
    return this.database;
  }

  /** Every item that is waiting. */
  async load() {
    const database = await this.open();
    const transaction = database.transaction(this.storeName, 'readonly');
    const request = transaction.objectStore(this.storeName).getAll();
    const items = await new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('The outbox could not be read.'));
    });
    return Array.isArray(items) ? items : [];
  }

  /** Write the whole queue down. */
  async save(items) {
    const database = await this.open();
    const transaction = database.transaction(this.storeName, 'readwrite');
    const objectStore = transaction.objectStore(this.storeName);
    objectStore.clear();
    for (const item of items) {
      objectStore.put(item);
    }
    await new Promise((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error || new Error('The outbox could not be saved.'));
      transaction.onabort = () => reject(transaction.error || new Error('The outbox save was undone.'));
    });
  }
}

/**
 * The store for this browser, or null when the browser has no IndexedDB.
 *
 * Nothing is opened here: the database is only touched when the queue is
 * actually read or written.
 */
export function createIndexedDbStore(options = {}) {
  const source = options.indexedDb !== undefined
    ? options.indexedDb
    : (typeof globalThis !== 'undefined' ? globalThis.indexedDB || null : null);
  if (!source) {
    return null;
  }
  return new IndexedDbStore({ ...options, indexedDb: source });
}

// ------------------------------------------------------------------- outbox

/**
 * A queue of work that has not reached the PC yet.
 *
 * The queue holds descriptors, not actions: `{ id, kind, payload, createdAt,
 * attempts, nextAttemptAt }`. The page gives the executor over when it
 * flushes, so a queued item is nothing but data and can be written down.
 */
export class Outbox {
  constructor({
    maxLength = MAX_QUEUE_LENGTH,
    baseBackoffMs = BASE_BACKOFF_MS,
    maxBackoffMs = MAX_BACKOFF_MS,
    now = Date.now,
    store = null,
    dedupeWindowMs = DEDUPE_WINDOW_MS,
  } = {}) {
    this.maxLength = maxLength;
    this.baseBackoffMs = baseBackoffMs;
    this.maxBackoffMs = maxBackoffMs;
    this.now = now;
    this.store = store;
    this.dedupeWindowMs = dedupeWindowMs;
    /** The items that are waiting. */
    this.items = [];
    /** The keys that were sent, with the time they went out. */
    this.sentKeys = new Map();
    /** How many items had to be thrown away because the queue was full. */
    this.dropped = 0;
    /** The last storage failure, empty when the store is healthy. */
    this.storageError = '';
  }

  /** How many items are waiting. */
  get length() {
    return this.items.length;
  }

  /** Give the outbox a store to keep the queue in. */
  useStore(store) {
    this.store = store || null;
    return this;
  }

  /**
   * Add work to the queue.
   *
   * The descriptor is plain data: a kind and a payload. Work that is equal to
   * something that is already waiting, or to something that was sent inside
   * the dedupe window, is not queued a second time. The item that is already
   * there keeps its attempt state, so a repeated push cannot shorten the
   * wait.
   *
   * Returns `{ item, duplicate, sent, persisted }`.
   */
  async push(descriptor) {
    const { kind, payload } = readDescriptor(descriptor);
    const id = idempotencyKey(kind, payload);
    const waiting = this.items.find((item) => item.id === id);
    if (waiting) {
      return { item: waiting, duplicate: true, sent: false, persisted: true };
    }
    if (this.sentRecently(id)) {
      return { item: { id, kind, payload }, duplicate: true, sent: true, persisted: true };
    }
    const item = {
      id,
      kind,
      payload,
      createdAt: this.now(),
      attempts: 0,
      nextAttemptAt: this.now(),
    };
    this.items.push(item);
    while (this.items.length > this.maxLength) {
      this.items.shift();
      this.dropped += 1;
    }
    const persisted = await this.persist();
    return { item, duplicate: false, sent: false, persisted };
  }

  /**
   * Forget the queued work that is equal to this one.
   *
   * The page calls this when it managed to do the work itself, so the queue
   * does not do it a second time.
   */
  async discard(kind, payload) {
    const id = idempotencyKey(kind, payload === undefined ? {} : payload);
    const before = this.items.length;
    this.items = this.items.filter((item) => item.id !== id);
    if (this.items.length === before) {
      return false;
    }
    await this.persist();
    return true;
  }

  /** How long to wait before the next attempt, in milliseconds. */
  backoffFor(attempts) {
    const wait = this.baseBackoffMs * (2 ** Math.max(0, attempts - 1));
    return Math.min(wait, this.maxBackoffMs);
  }

  /** The items that may be tried now. */
  ready(now = this.now()) {
    return this.items.filter((item) => item.nextAttemptAt <= now);
  }

  /**
   * Send the items that are ready.
   *
   * The executor comes from the page: it takes one descriptor and does the
   * call it stands for. An item that succeeds is removed and its key is
   * remembered for a short while, so the same work is not sent twice. An item
   * that fails stays in the queue and waits longer, with the wait growing and
   * bounded.
   */
  async flush(executor) {
    if (typeof executor !== 'function') {
      throw new Error('The outbox needs an executor to send the queued work.');
    }
    const results = { sent: 0, failed: 0, remaining: this.items.length };
    for (const item of this.ready()) {
      try {
        await executor(item);
      } catch (error) {
        item.attempts += 1;
        item.nextAttemptAt = this.now() + this.backoffFor(item.attempts);
        results.failed += 1;
        continue;
      }
      this.items = this.items.filter((other) => other.id !== item.id);
      this.sentKeys.set(item.id, this.now());
      results.sent += 1;
    }
    this.pruneSentKeys();
    await this.persist();
    results.remaining = this.items.length;
    return results;
  }

  /**
   * Read the queue back from the store.
   *
   * The items that are already in memory win when they hold the newer
   * attempt state. The oldest items are dropped when the store holds more
   * than the queue allows.
   */
  async restore() {
    if (!this.store) {
      return 0;
    }
    let saved = [];
    try {
      saved = await this.store.load();
    } catch (error) {
      this.storageError = messageOf(error);
      return 0;
    }
    const byId = new Map();
    for (const item of this.items) {
      byId.set(item.id, item);
    }
    for (const raw of Array.isArray(saved) ? saved : []) {
      const item = readStoredItem(raw);
      if (!item) {
        continue;
      }
      const existing = byId.get(item.id);
      if (!existing) {
        byId.set(item.id, item);
        continue;
      }
      if (item.attempts > existing.attempts || item.nextAttemptAt > existing.nextAttemptAt) {
        byId.set(item.id, item);
      }
    }
    const merged = [...byId.values()].sort((one, other) => one.createdAt - other.createdAt);
    while (merged.length > this.maxLength) {
      merged.shift();
      this.dropped += 1;
    }
    this.items = merged;
    await this.persist();
    return this.items.length;
  }

  /** Write the queue down, and say whether it worked. */
  async persist() {
    if (!this.store) {
      return true;
    }
    try {
      await this.store.save(this.items.map(cloneItem));
      this.storageError = '';
      return true;
    } catch (error) {
      this.storageError = messageOf(error);
      return false;
    }
  }

  /** Whether this work was sent inside the dedupe window. */
  sentRecently(id) {
    const at = this.sentKeys.get(id);
    if (at === undefined) {
      return false;
    }
    return this.now() - at < this.dedupeWindowMs;
  }

  /** Forget the keys that are older than the dedupe window. */
  pruneSentKeys() {
    for (const [id, at] of this.sentKeys) {
      if (this.now() - at >= this.dedupeWindowMs) {
        this.sentKeys.delete(id);
      }
    }
  }

  /** Forget everything that is waiting. */
  async clear() {
    this.items = [];
    this.sentKeys.clear();
    await this.persist();
  }
}
