"""Replay protection for signed bridge requests.

The signature alone proves that a request was produced by a paired device. It
does not prove that the request is new. The nonce registry and the timestamp
window together make every accepted request single use.
"""
import threading
import time

from remote.protocol import NONCE_TTL_SECONDS, ProtocolError


class ReplayGuard:
    """Remembers recently used nonces so a captured request cannot be reused.

    The guard is process local. A restart forgets old nonces, so the timestamp
    window remains the outer bound on how old an accepted request may be.
    """

    def __init__(self, ttl_seconds: int = NONCE_TTL_SECONDS, *, now=time.monotonic):
        if not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise ValueError('Nonce TTL must be a positive number of seconds')
        self._ttl = ttl_seconds
        self._now = now
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, nonce: str) -> None:
        """Record the nonce, or raise `ProtocolError` if it was already used."""
        if not isinstance(nonce, str) or not nonce:
            raise ProtocolError('Missing bridge nonce.')
        moment = self._now()
        with self._lock:
            expired = [seen for seen, at in self._seen.items() if at <= moment - self._ttl]
            for seen in expired:
                del self._seen[seen]
            if nonce in self._seen:
                raise ProtocolError('Bridge nonce has already been used.')
            self._seen[nonce] = moment

    def clear(self) -> None:
        """Forget every nonce. Used when the pairing set changes."""
        with self._lock:
            self._seen.clear()
