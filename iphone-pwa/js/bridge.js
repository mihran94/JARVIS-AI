// The JARVIS bridge client for the phone and the iPhone.
//
// The signing scheme is the one in `remote/protocol.py` on the desktop and
// in `core/windows/BridgeClient.kt` on the Android client. The three sides
// must agree byte for byte:
//
//     canonical = METHOD \n PATH \n TIMESTAMP \n NONCE \n SHA256(BODY)
//     signature = HMAC-SHA256(canonical, secret), lowercase hex
//
// The timestamp is in milliseconds and the nonce is 16 random bytes in hex.
//
// The secret never leaves this page. It is held in memory only, it is never
// written to storage, it is never put in a URL and it is never logged.

export const PROTOCOL_VERSION = 1;

export const KEY_ID_HEADER = 'X-Jarvis-Key-Id';
export const TIMESTAMP_HEADER = 'X-Jarvis-Timestamp';
export const NONCE_HEADER = 'X-Jarvis-Nonce';
export const SIGNATURE_HEADER = 'X-Jarvis-Signature';

/** The shortest secret the desktop will accept. */
export const MINIMUM_SECRET_LENGTH = 32;

/** How far the clock may be out before the desktop refuses the request. */
export const MAX_CLOCK_SKEW_SECONDS = 300;

const encoder = new TextEncoder();

/** Lowercase hex of a byte buffer. */
export function toHex(bytes) {
  return Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

/** The SHA-256 of a string, as lowercase hex. */
export async function sha256Hex(value) {
  const digest = await crypto.subtle.digest('SHA-256', encoder.encode(value));
  return toHex(digest);
}

/** The exact string both sides sign. The field order is part of the protocol. */
export function canonicalString(method, path, timestamp, nonce, bodyDigest) {
  return [method.toUpperCase(), path, timestamp, nonce, bodyDigest].join('\n');
}

/** The HMAC-SHA256 of the canonical string, as lowercase hex. */
export async function signCanonical(canonical, secret) {
  const key = await crypto.subtle.importKey(
    'raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(canonical));
  return toHex(signature);
}

/** The signature for one request. */
export async function signRequest({ method, path, timestamp, nonce, body = '', secret }) {
  const canonical = canonicalString(method, path, timestamp, nonce, await sha256Hex(body));
  return signCanonical(canonical, secret);
}

/**
 * A nonce of 16 random bytes, as 32 lowercase hex characters.
 *
 * The default is an arrow function on purpose. A bare `crypto.getRandomValues`
 * loses the binding to the crypto object, and browsers refuse it.
 */
export function makeNonce(randomBytes = (bytes) => crypto.getRandomValues(bytes)) {
  return toHex(randomBytes(new Uint8Array(16)));
}

/**
 * Whether a bridge URL may be used.
 *
 * HTTPS is required. Plain HTTP is only allowed for a loopback address and
 * only when the caller says so, which is for a local development proxy and
 * never for a real bridge.
 */
export function checkBridgeUrl(rawUrl, { allowLoopbackHttp = false } = {}) {
  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch (error) {
    throw new Error('Enter a full bridge URL, for example https://pc.example.lan');
  }
  if (parsed.username || parsed.password) {
    throw new Error('Remove the user name and password from the bridge URL.');
  }
  if (parsed.protocol === 'https:') {
    return parsed;
  }
  const loopback = parsed.hostname === '127.0.0.1' || parsed.hostname === '::1' ||
    parsed.hostname === 'localhost';
  if (parsed.protocol === 'http:' && loopback && allowLoopbackHttp) {
    return parsed;
  }
  throw new Error('The bridge URL must use HTTPS.');
}

/** A bridge failure that carries the status the desktop answered with. */
export class BridgeError extends Error {
  constructor(message, { status = 0, path = '' } = {}) {
    super(message);
    this.name = 'BridgeError';
    this.status = status;
    this.path = path;
  }
}

/**
 * The client for one paired device.
 *
 * It holds the base URL, the key id and the shared secret, and it signs
 * every request. The fetch function, the clock and the random source are
 * injected so the whole client can be tested without a network.
 */
export class BridgeClient {
  constructor({
    baseUrl,
    keyId,
    secret,
    fetchImpl = globalThis.fetch,
    now = Date.now,
    randomBytes = (bytes) => crypto.getRandomValues(bytes),
    allowLoopbackHttp = false,
  }) {
    this.baseUrl = checkBridgeUrl(baseUrl, { allowLoopbackHttp }).toString().replace(/\/+$/, '');
    if (typeof keyId !== 'string' || !keyId.trim()) {
      throw new Error('A device key id is required.');
    }
    if (typeof secret !== 'string' || secret.length < MINIMUM_SECRET_LENGTH) {
      throw new Error(`The pairing secret needs at least ${MINIMUM_SECRET_LENGTH} characters.`);
    }
    this.keyId = keyId.trim();
    this.secret = secret;
    this.fetchImpl = fetchImpl;
    this.now = now;
    this.randomBytes = randomBytes;
  }

  /** One signed request. */
  async request(method, path, body = '') {
    if (typeof path !== 'string' || !path.startsWith('/')) {
      throw new BridgeError('A bridge path must start with /.', { path });
    }
    const timestamp = String(this.now());
    const nonce = makeNonce(this.randomBytes);
    const signature = await signRequest({
      method, path, timestamp, nonce, body, secret: this.secret,
    });
    const headers = {
      [KEY_ID_HEADER]: this.keyId,
      [TIMESTAMP_HEADER]: timestamp,
      [NONCE_HEADER]: nonce,
      [SIGNATURE_HEADER]: signature,
    };
    if (body) {
      headers['Content-Type'] = 'application/json';
    }
    let response;
    try {
      response = await this.fetchImpl(this.baseUrl + path, {
        method: method.toUpperCase(),
        headers,
        body: body || undefined,
        cache: 'no-store',
        credentials: 'omit',
        redirect: 'error',
      });
    } catch (error) {
      throw new BridgeError('The PC could not be reached. Check the bridge URL.', { path });
    }
    const text = await response.text();
    let payload = {};
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (error) {
        throw new BridgeError(`The PC answered with an unreadable body (HTTP ${response.status}).`,
          { status: response.status, path });
      }
    }
    if (!response.ok) {
      const message = payload && payload.error ? payload.error : `The PC answered HTTP ${response.status}.`;
      throw new BridgeError(message, { status: response.status, path });
    }
    return payload;
  }

  /** The state of the PC. */
  async status() {
    return this.request('GET', '/api/status');
  }

  /** Every job the PC knows. */
  async jobs() {
    const payload = await this.request('GET', '/api/jobs');
    return Array.isArray(payload.jobs) ? payload.jobs : [];
  }

  /** One job, with its progress. */
  async job(jobId) {
    return this.request('GET', `/api/jobs/${encodeURIComponent(jobId)}`);
  }

  /** Send a job for the owner to approve. */
  async submitJob({ kind = 'CUSTOM', title, payload = '', requireApproval = true }) {
    if (typeof title !== 'string' || !title.trim()) {
      throw new BridgeError('Give the task a title.');
    }
    return this.request('POST', '/api/jobs', JSON.stringify({
      kind, title: title.trim(), payload, requireApproval,
    }));
  }

  /** Cancel a job that has not finished. */
  async cancelJob(jobId) {
    return this.request('POST', `/api/jobs/${encodeURIComponent(jobId)}/cancel`);
  }

  /** Ask the desktop to answer a message. */
  async chat(message, { consent = false } = {}) {
    return this.request('POST', '/api/chat', JSON.stringify({ message, consent }));
  }

  /** The memory the desktop is willing to share. */
  async memory() {
    const payload = await this.request('GET', '/api/memory');
    return Array.isArray(payload.memory) ? payload.memory : [];
  }

  /** Send one memory entry to the desktop. */
  async remember(text, source = 'phone') {
    return this.request('POST', '/api/memory', JSON.stringify({ text, source }));
  }

  /** The notifications the desktop has waiting. */
  async notifications() {
    const payload = await this.request('GET', '/api/notifications');
    return Array.isArray(payload.notifications) ? payload.notifications : [];
  }

  /** Tell the desktop that a notification was seen. */
  async acknowledge(notificationId) {
    return this.request('POST', `/api/notifications/${encodeURIComponent(notificationId)}/ack`);
  }
}
