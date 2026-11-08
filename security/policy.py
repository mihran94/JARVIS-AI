"""Approval boundary; approvals cannot survive stop/resume or be reused."""
from dataclasses import dataclass
from threading import RLock
import uuid


class Stopped(RuntimeError):
    pass


class Denied(RuntimeError):
    pass


@dataclass(frozen=True)
class Action:
    kind: str
    target: str
    digest: str = ''


class Policy:
    def __init__(self):
        self._lock = RLock()
        self._generation = 0
        self._stopped = False
        self._grants = {}

    @property
    def stopped(self):
        with self._lock:
            return self._stopped

    def ticket(self):
        with self._lock:
            if self._stopped:
                raise Stopped('Emergency stop is active. Resume explicitly.')
            return self._generation

    def check(self, ticket):
        with self._lock:
            if self._stopped or ticket != self._generation:
                raise Stopped('Operation cancelled by emergency stop.')

    def stop(self):
        with self._lock:
            self._stopped = True
            self._generation += 1
            self._grants.clear()

    def resume(self):
        with self._lock:
            self._stopped = False

    def approve(self, action, confirm):
        ticket = self.ticket()
        if not confirm(action):
            raise Denied('Action declined.')
        with self._lock:
            self.check(ticket)
            token = uuid.uuid4().hex
            self._grants[token] = (ticket, action)
            return token

    def execute(self, action, token, operation):
        # Serialize short mutations with stop: nothing new starts after stop.
        with self._lock:
            grant = self._grants.pop(token, None)
            if grant is None or grant[1] != action:
                raise Denied('Missing or mismatched one-use approval.')
            self.check(grant[0])
            return operation()
