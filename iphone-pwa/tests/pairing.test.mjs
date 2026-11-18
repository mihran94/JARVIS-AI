// The pairing code the desktop writes and the phone reads.
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  PAIRING_FORMAT, buildPairingPayload, isPairingValid, parsePairingPayload,
} from '../js/pairing.js';

const SECRET = 'shared-secret-for-tests-0123456789abcdef';
const NOW = 1700000000;

test('a code that is written can be read back', () => {
  const payload = buildPairingPayload({
    bridgeUrl: 'https://pc.example.lan:8765',
    keyId: 'iphone-mihran-01',
    secret: SECRET,
    expiresAt: NOW + 600,
  });
  const pairing = parsePairingPayload(payload, { now: NOW });
  assert.equal(pairing.bridgeUrl, 'https://pc.example.lan:8765');
  assert.equal(pairing.keyId, 'iphone-mihran-01');
  assert.equal(pairing.secret, SECRET);
  assert.equal(pairing.expiresAt, NOW + 600);
});

test('the format line is the agreed one', () => {
  const payload = buildPairingPayload({
    bridgeUrl: 'https://pc.example.lan', keyId: 'k', secret: SECRET, expiresAt: NOW + 60,
  });
  assert.equal(payload.split('\n')[0], PAIRING_FORMAT);
});

test('a code with another format is refused', () => {
  assert.throws(() => parsePairingPayload('SOMETHING-ELSE\nbridge=https://pc.example.lan'),
    /not a JARVIS pairing code/);
});

test('a code without a bridge is refused', () => {
  assert.throws(() => parsePairingPayload(`${PAIRING_FORMAT}\nkey=k\nsecret=${SECRET}\nexpires=1`),
    /no bridge address/);
});

test('a code without a key is refused', () => {
  assert.throws(() => parsePairingPayload(`${PAIRING_FORMAT}\nbridge=https://pc.example.lan\nsecret=${SECRET}\nexpires=1`),
    /no device key id/);
});

test('a code with a short secret is refused', () => {
  assert.throws(() => parsePairingPayload(
    `${PAIRING_FORMAT}\nbridge=https://pc.example.lan\nkey=k\nsecret=short\nexpires=1`),
  /no usable secret/);
});

test('an expired code is refused', () => {
  const payload = buildPairingPayload({
    bridgeUrl: 'https://pc.example.lan', keyId: 'k', secret: SECRET, expiresAt: NOW - 1,
  });
  assert.throws(() => parsePairingPayload(payload, { now: NOW }), /expired/);
});

test('a code that does not use https is refused', () => {
  const payload = buildPairingPayload({
    bridgeUrl: 'http://pc.example.lan', keyId: 'k', secret: SECRET, expiresAt: NOW + 60,
  });
  assert.throws(() => parsePairingPayload(payload, { now: NOW }), /HTTPS/);
});

test('a damaged code is refused', () => {
  assert.throws(() => parsePairingPayload(`${PAIRING_FORMAT}\nthis line has no equals sign`),
    /damaged/);
});

test('an empty code is refused', () => {
  assert.throws(() => parsePairingPayload('   '), /empty/);
});

test('a code cannot be written with a short secret', () => {
  assert.throws(() => buildPairingPayload({
    bridgeUrl: 'https://pc.example.lan', keyId: 'k', secret: 'short', expiresAt: NOW,
  }), /at least 32 characters/);
});

test('the validity check agrees with the parser', () => {
  const payload = buildPairingPayload({
    bridgeUrl: 'https://pc.example.lan', keyId: 'k', secret: SECRET, expiresAt: NOW + 60,
  });
  const pairing = parsePairingPayload(payload, { now: NOW });
  assert.equal(isPairingValid(pairing, { now: NOW }), true);
  assert.equal(isPairingValid(pairing, { now: NOW + 61 }), false);
  assert.equal(isPairingValid(null), false);
});

test('the certificate fingerprint travels with the code', () => {
  const fingerprint = 'a'.repeat(64);
  const payload = buildPairingPayload({
    bridgeUrl: 'https://pc.example.lan:8765',
    keyId: 'iphone-mihran-01',
    secret: SECRET,
    expiresAt: NOW + 600,
    fingerprint,
  });
  const pairing = parsePairingPayload(payload, { now: NOW });
  assert.equal(pairing.fingerprint, fingerprint);
});

test('a code without a certificate still pairs', () => {
  const payload = buildPairingPayload({
    bridgeUrl: 'https://pc.example.lan:8765',
    keyId: 'iphone-mihran-01',
    secret: SECRET,
    expiresAt: NOW + 600,
  });
  const pairing = parsePairingPayload(payload, { now: NOW });
  assert.equal(pairing.fingerprint, '');
});

test('a damaged fingerprint is refused rather than trusted', () => {
  const payload = [
    PAIRING_FORMAT,
    'bridge=https://pc.example.lan:8765',
    'key=iphone-mihran-01',
    `secret=${SECRET}`,
    `expires=${NOW + 600}`,
    'fp=not-a-fingerprint',
  ].join('\n');
  assert.throws(() => parsePairingPayload(payload, { now: NOW }),
    /damaged certificate fingerprint/);
});
