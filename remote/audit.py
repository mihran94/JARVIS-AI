"""Audit log for the bridge.

Every request is recorded, so the owner can see what a paired device asked
for and what the bridge answered. The log is deliberately narrow: it records
the key id, the method, the path, the result and a digest of the body.

It never records a secret, an API key, a pairing secret or the body itself.
A chat message or a memory entry is private content, so only its SHA-256
digest is kept, and only the first part of it, which is enough to tell two
requests apart.

The log is in memory and is bounded, so a flood of requests cannot grow it
without limit.
"""
from dataclasses import dataclass
import hashlib
import threading
import time

#: How many entries the audit log keeps.
MAX_ENTRIES = 500

#: How much of the body digest is kept.
DIGEST_PREFIX_LENGTH = 16


@dataclass(frozen=True)
class AuditEntry:
    """One recorded request."""

    at: int
    key_id: str
    method: str
    path: str
    status: int
    body_digest: str
    note: str = ''

    def to_json(self) -> dict:
        return {
            'at': self.at,
            'key_id': self.key_id,
            'method': self.method,
            'path': self.path,
            'status': self.status,
            'body_digest': self.body_digest,
            'note': self.note,
        }


def body_digest(body: str) -> str:
    """The short digest of a request body. The body itself is never stored."""
    if not body:
        return ''
    digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
    return digest[:DIGEST_PREFIX_LENGTH]


class AuditLog:
    """A bounded, in-memory record of the bridge requests."""

    def __init__(self, *, now=time.time, limit: int = MAX_ENTRIES):
        self._now = now
        self._limit = limit
        self._entries: list[AuditEntry] = []
        self._lock = threading.RLock()

    def record(self, key_id: str, method: str, path: str, status: int, body: str = '',
               note: str = '') -> AuditEntry:
        """Record one request and return the entry."""
        entry = AuditEntry(
            at=int(self._now() * 1000),
            key_id=key_id or '',
            method=(method or '').upper(),
            path=path or '',
            status=int(status),
            body_digest=body_digest(body),
            note=note,
        )
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._limit:
                del self._entries[:len(self._entries) - self._limit]
        return entry

    def entries(self, limit: int = 100) -> list[AuditEntry]:
        """The most recent entries, newest last."""
        with self._lock:
            return list(self._entries[-limit:])

    def clear(self) -> None:
        """Forget every entry."""
        with self._lock:
            self._entries.clear()
