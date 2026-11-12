"""Notifications that travel between the desktop and the paired devices.

A notification is a short piece of information for the other side: a job that
finished, a memory that arrived, an alert the desktop raised. The store keeps
them until they are acknowledged, so a phone that was offline can still show
what it missed.

The store holds no secrets. A notification carries a title, a body and a
level, and it is bounded so a flood cannot grow it without limit.
"""
from dataclasses import dataclass
import threading
import time
import uuid

#: The most notifications that are kept.
MAX_NOTIFICATIONS = 100

#: The levels a notification may have.
LEVELS = ('info', 'warning', 'error')

#: The most characters a title or a body may hold.
MAX_LENGTH = 500


class NotificationError(RuntimeError):
    """A notification was refused."""


@dataclass(frozen=True)
class Notification:
    """One notification."""

    id: str
    title: str
    body: str
    level: str
    created_at: int
    acknowledged: bool = False

    def to_json(self) -> dict:
        return {
            'id': self.id,
            'title': self.title,
            'body': self.body,
            'level': self.level,
            'created_at': self.created_at,
            'acknowledged': self.acknowledged,
        }


class NotificationStore:
    """Pending notifications, oldest first."""

    def __init__(self, *, now=time.time, limit: int = MAX_NOTIFICATIONS):
        self._now = now
        self._limit = limit
        self._items: list[Notification] = []
        self._lock = threading.RLock()

    def push(self, title: str, body: str = '', level: str = 'info') -> Notification:
        """Record a notification and return it."""
        if not isinstance(title, str) or not title.strip():
            raise NotificationError('A notification needs a title.')
        if not isinstance(body, str):
            raise NotificationError('A notification body must be text.')
        if level not in LEVELS:
            raise NotificationError('Unknown notification level.')
        if len(title) > MAX_LENGTH or len(body) > MAX_LENGTH:
            raise NotificationError('That notification is too long.')
        item = Notification(
            id=uuid.uuid4().hex,
            title=title.strip(),
            body=body.strip(),
            level=level,
            created_at=int(self._now() * 1000),
        )
        with self._lock:
            self._items.append(item)
            while len(self._items) > self._limit:
                del self._items[0]
        return item

    def pending(self, limit: int = 50) -> list[Notification]:
        """The notifications that were not acknowledged yet, oldest first."""
        with self._lock:
            return [item for item in self._items if not item.acknowledged][-limit:]

    def all(self, limit: int = 100) -> list[Notification]:
        """Every notification, oldest first."""
        with self._lock:
            return list(self._items[-limit:])

    def acknowledge(self, notification_id: str) -> bool:
        """Mark one notification as acknowledged."""
        with self._lock:
            for index, item in enumerate(self._items):
                if item.id == notification_id:
                    if item.acknowledged:
                        return False
                    self._items[index] = Notification(
                        id=item.id, title=item.title, body=item.body, level=item.level,
                        created_at=item.created_at, acknowledged=True)
                    return True
            return False

    def clear(self) -> None:
        """Forget every notification."""
        with self._lock:
            self._items.clear()
