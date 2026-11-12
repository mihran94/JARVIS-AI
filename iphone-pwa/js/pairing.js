// Reading the pairing code that the Windows desktop displays.
//
// The desktop writes a short text block into a QR code. The phone scans the
// code and reads the same information from it. The format is one field per
// line, so it can also be pasted by hand when the camera is not usable.
//
//     JARVIS-BRIDGE-v1
//     bridge=https://pc.example.lan:8765
//     key=iphone-mihran-01
//     secret=<one-time secret>
//     expires=1764000000
//
// The secret is only ever held in memory. It is never written to storage and
// it is never sent anywhere except to the bridge that the owner paired.

/** The first line of every pairing code. */
export const PAIRING_FORMAT = 'JARVIS-BRIDGE-v1';

/** How long a pairing code stays usable, in seconds. */
export const DEFAULT_LIFETIME_SECONDS = 900;

/** The shortest secret the desktop accepts. */
export const MINIMUM_SECRET_LENGTH = 32;

/**
 * Build the text of a pairing code.
 *
 * The desktop uses this to draw the QR code, and the tests use it to check
 * that the phone reads back exactly what the desktop wrote.
 */
export function buildPairingPayload({ bridgeUrl, keyId, secret, expiresAt = 0 }) {
  if (typeof bridgeUrl !== 'string' || !bridgeUrl.trim()) {
    throw new Error('A bridge URL is required.');
  }
  if (typeof keyId !== 'string' || !keyId.trim()) {
    throw new Error('A device key id is required.');
  }
  if (typeof secret !== 'string' || secret.length < MINIMUM_SECRET_LENGTH) {
    throw new Error(`The pairing secret needs at least ${MINIMUM_SECRET_LENGTH} characters.`);
  }
  return [
    PAIRING_FORMAT,
    `bridge=${bridgeUrl.trim()}`,
    `key=${keyId.trim()}`,
    `secret=${secret}`,
    `expires=${Math.floor(expiresAt)}`,
  ].join('\n');
}

/**
 * Read a pairing code.
 *
 * The code is checked before it is used: the format has to be the one this
 * page knows, the bridge URL has to be HTTPS, the secret has to be long
 * enough and the code must not have expired.
 */
export function parsePairingPayload(text, { now = Math.floor(Date.now() / 1000) } = {}) {
  if (typeof text !== 'string' || !text.trim()) {
    throw new Error('The pairing code is empty.');
  }
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (lines[0] !== PAIRING_FORMAT) {
    throw new Error('That is not a JARVIS pairing code.');
  }
  const fields = {};
  for (const line of lines.slice(1)) {
    const separator = line.indexOf('=');
    if (separator <= 0) {
      throw new Error('The pairing code is damaged.');
    }
    fields[line.slice(0, separator).trim().toLowerCase()] = line.slice(separator + 1).trim();
  }
  const bridgeUrl = fields.bridge || '';
  const keyId = fields.key || '';
  const secret = fields.secret || '';
  const expiresAt = Number.parseInt(fields.expires || '0', 10);
  if (!bridgeUrl) {
    throw new Error('The pairing code has no bridge address.');
  }
  if (!keyId) {
    throw new Error('The pairing code has no device key id.');
  }
  if (secret.length < MINIMUM_SECRET_LENGTH) {
    throw new Error('The pairing code has no usable secret.');
  }
  if (!Number.isFinite(expiresAt) || expiresAt <= 0) {
    throw new Error('The pairing code has no expiry.');
  }
  if (expiresAt <= now) {
    throw new Error('That pairing code has expired. Pair the phone again.');
  }
  let parsed;
  try {
    parsed = new URL(bridgeUrl);
  } catch (error) {
    throw new Error('The pairing code has an unreadable bridge address.');
  }
  if (parsed.protocol !== 'https:') {
    throw new Error('The pairing code does not use HTTPS.');
  }
  // A bridge address is a host and a port, so the empty path of a bare
  // address is dropped again.
  const address = parsed.pathname === '/' && !parsed.search && !parsed.hash
    ? `${parsed.origin}`
    : parsed.toString();
  return { bridgeUrl: address, keyId, secret, expiresAt };
}

/** Whether a pairing code is still usable. */
export function isPairingValid(pairing, { now = Math.floor(Date.now() / 1000) } = {}) {
  if (!pairing || typeof pairing.expiresAt !== 'number') {
    return false;
  }
  return pairing.expiresAt > now;
}
