"""Canonical JARVIS desktop/mobile bridge protocol, version 1.

The Android client signs every request in `core/windows/BridgeClient.kt`
(jarvis-blue-android). This module is the desktop reference implementation of
the same scheme, and both halves must agree byte for byte. The shared vectors
are pinned in `tests/test_bridge_protocol.py` so a change on either side fails
loudly instead of silently breaking the pair.

Transport rules that are part of the protocol:

- HTTPS/TLS only. There is no plaintext fallback for the control API.
- Every request carries a HMAC-SHA256 signature over a canonical string built
  from the method, path, timestamp, nonce and body digest.
- The timestamp plus the nonce makes each signature single use, so a captured
  request cannot be replayed.
- The Windows machine is expected to sit behind a VPN or a private tunnel.
  No control port is published to the public internet.
"""
import hashlib
import hmac
import time

PROTOCOL_VERSION = 1

#: Key id sent by the current Android client. A second paired phone must use a
#: distinct key id so that one revocation does not affect the other.
KEY_ID = 'jarvis-blue-mobile-v1'

KEY_ID_HEADER = 'X-Jarvis-Key-Id'
TIMESTAMP_HEADER = 'X-Jarvis-Timestamp'
NONCE_HEADER = 'X-Jarvis-Nonce'
SIGNATURE_HEADER = 'X-Jarvis-Signature'

#: Requests older or newer than this are rejected before any signature work.
MAX_CLOCK_SKEW_SECONDS = 300

#: How long a nonce is remembered. Must stay above the clock skew window so a
#: request cannot be replayed after its nonce expired.
NONCE_TTL_SECONDS = 900


class ProtocolError(RuntimeError):
    """The request does not satisfy the bridge protocol."""


def sha256_hex(body: str) -> str:
    """SHA-256 of the raw body, as lowercase hex."""
    if not isinstance(body, str):
        raise TypeError('Body must be a string')
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def canonical_string(method: str, path: str, timestamp: str, nonce: str, body: str) -> str:
    """The exact string both sides sign. Field order is part of the protocol."""
    if not isinstance(method, str) or not isinstance(path, str):
        raise TypeError('Method and path must be strings')
    if not isinstance(timestamp, str) or not isinstance(nonce, str):
        raise TypeError('Timestamp and nonce must be strings')
    return '\n'.join([method.upper(), path, timestamp, nonce, sha256_hex(body)])


def sign(method: str, path: str, timestamp: str, body: str, secret: str, nonce: str) -> str:
    """Return the lowercase hex HMAC-SHA256 of the canonical string."""
    if not isinstance(secret, str) or not secret:
        raise ValueError('A shared secret is required')
    canonical = canonical_string(method, path, timestamp, nonce, body)
    return hmac.new(secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()


def verify(method: str, path: str, timestamp: str, body: str, secret: str, nonce: str,
           provided: str) -> None:
    """Raise `ProtocolError` unless the signature matches exactly."""
    if not isinstance(provided, str) or not provided:
        raise ProtocolError('Missing bridge signature.')
    expected = sign(method, path, timestamp, body, secret, nonce)
    if not hmac.compare_digest(expected, provided):
        raise ProtocolError('Invalid bridge signature.')


def timestamp_seconds(timestamp: str) -> float:
    """Convert the millisecond timestamp header into seconds."""
    try:
        return int(timestamp) / 1000.0
    except (TypeError, ValueError):
        raise ProtocolError('Invalid bridge timestamp.') from None


def check_timestamp(timestamp: str, *, now: float | None = None,
                    max_skew_seconds: int = MAX_CLOCK_SKEW_SECONDS) -> None:
    """Reject a request whose timestamp is outside the allowed clock window."""
    moment = timestamp_seconds(timestamp)
    current = time.time() if now is None else now
    if abs(current - moment) > max_skew_seconds:
        raise ProtocolError('Bridge timestamp outside the allowed window.')


def normalize_headers(headers: dict | None) -> dict:
    """Lower-case header names so lookups match any HTTP client casing."""
    if not headers:
        return {}
    if not isinstance(headers, dict):
        raise TypeError('Headers must be a mapping')
    return {str(name).lower(): str(value) for name, value in headers.items()}
