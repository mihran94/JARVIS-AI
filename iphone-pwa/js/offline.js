// The outbox for a phone that is out of reach.
//
// When the bridge cannot be reached, the actions the person asked for are
// kept here and sent when the connection returns. The queue is bounded, the
// attempts are spaced out, and nothing is lost silently: the page shows how
// many items are waiting.

/** How many items the outbox keeps. */
export const MAX_QUEUE_LENGTH = 20;

/** The first retry waits this many milliseconds. */
export const BASE_BACKOFF_MS = 2000;

/** The retries never wait longer than this. */
export const MAX_BACKOFF_MS = 60000;

/** A queue of actions that have not reached the PC yet. */
export class Outbox {
  constructor({ maxLength = MAX_QUEUE_LENGTH, baseBackoffMs = BASE_BACKOFF_MS,
    maxBackoffMs = MAX_BACKOFF_MS, now = Date.now } = {}) {
    this.maxLength = maxLength;
    this.baseBackoffMs = baseBackoffMs;
    this.maxBackoffMs = maxBackoffMs;
    this.now = now;
    this.items = [];
  }

  /** How many items are waiting. */
  get length() {
    return this.items.length;
  }

  /** Add an action. The oldest is dropped when the queue is full. */
  push(action) {
    if (!action || typeof action.run !== 'function') {
      throw new Error('An outbox item needs something to run.');
    }
    this.items.push({
      id: `${this.now()}-${this.items.length}`,
      action,
      attempts: 0,
      nextAttemptAt: this.now(),
    });
    while (this.items.length > this.maxLength) {
      this.items.shift();
    }
    return this.items[this.items.length - 1];
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
   * Run the items that are ready.
   *
   * An item that fails stays in the queue and waits longer. An item that
   * succeeds is removed. The results are reported so the page can say what
   * happened.
   */
  async flush(run) {
    const results = { sent: 0, failed: 0, remaining: this.items.length };
    for (const item of this.ready()) {
      try {
        await item.action.run();
        this.items = this.items.filter((other) => other.id !== item.id);
        results.sent += 1;
      } catch (error) {
        item.attempts += 1;
        item.nextAttemptAt = this.now() + this.backoffFor(item.attempts);
        results.failed += 1;
      }
    }
    results.remaining = this.items.length;
    return results;
  }

  /** Forget everything that is waiting. */
  clear() {
    this.items = [];
  }
}
