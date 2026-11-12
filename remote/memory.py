"""Memory that may be synchronised between the desktop and a paired phone.

The store is small and explicit. Every entry has a source, so the owner can
see where a memory came from, and the total size is bounded so a phone cannot
fill the desktop with text.

Nothing here is written to disk. The desktop decides separately whether to
persist the entries it receives.
"""
from dataclasses import dataclass
import threading
import time
import uuid

#: The most entries that are kept.
MAX_ENTRIES = 200

#: The most characters one entry may hold.
MAX_ENTRY_LENGTH = 2000

#: The most characters all entries may hold together.
MAX_TOTAL_CHARACTERS = 40000


class MemoryError_(RuntimeError):
    """A memory entry was refused."""


@dataclass(frozen=True)
class MemoryEntry:
    """One remembered item."""

    id: str
    text: str
    source: str
    created_at: int

    def to_json(self) -> dict:
        return {
            'id': self.id,
            'text': self.text,
            'source': self.source,
            'created_at': self.created_at,
        }


class MemoryStore:
    """The synchronised memory entries, newest last."""

    def __init__(self, *, now=time.time, limit: int = MAX_ENTRIES):
        self._now = now
        self._limit = limit
        self._entries: list[MemoryEntry] = []
        self._lock = threading.RLock()

    def append(self, text: str, source: str = 'phone') -> MemoryEntry:
        """Add one entry and return it."""
        if not isinstance(text, str) or not text.strip():
            raise MemoryError_('A memory entry needs some text.')
        if len(text) > MAX_ENTRY_LENGTH:
            raise MemoryError_('That memory entry is too long.')
        if not isinstance(source, str) or not source.strip():
            raise MemoryError_('A memory entry needs a source.')
        entry = MemoryEntry(
            id=uuid.uuid4().hex,
            text=text.strip(),
            source=source.strip()[:40],
            created_at=int(self._now() * 1000),
        )
        with self._lock:
            self._entries.append(entry)
            self._trim()
        return entry

    def entries(self, limit: int = 100) -> list[MemoryEntry]:
        """The most recent entries, oldest first."""
        with self._lock:
            return list(self._entries[-limit:])

    def total_characters(self) -> int:
        """How many characters the store holds."""
        with self._lock:
            return sum(len(entry.text) for entry in self._entries)

    def clear(self) -> None:
        """Forget every entry."""
        with self._lock:
            self._entries.clear()

    def _trim(self) -> None:
        """Drop the oldest entries until the store is inside its limits."""
        while len(self._entries) > self._limit:
            del self._entries[0]
        while self._entries and self.total_characters() > MAX_TOTAL_CHARACTERS:
            del self._entries[0]
