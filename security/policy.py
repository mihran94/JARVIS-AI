"""Approval boundary; approvals cannot survive stop/resume or be reused."""
from dataclasses import dataclass
from enum import Enum
from threading import RLock
import uuid


class Stopped(RuntimeError):
    pass


class Denied(RuntimeError):
    pass


class ApprovalMode(str, Enum):
    ASK = 'ask'
    AUTOMATIC = 'automatic'
    FULL = 'full'

    @classmethod
    def from_setting(cls, value):
        try:
            return cls(value)
        except ValueError:
            return cls.ASK


class ApprovalScope(Enum):
    ALWAYS = 'always'
    ROUTINE = 'routine'
    LOCAL_WRITE = 'local_write'


@dataclass(frozen=True)
class Action:
    kind: str
    target: str
    digest: str = ''
    approval_scope: ApprovalScope = ApprovalScope.ALWAYS


@dataclass(frozen=True)
class Decision:
    """One thing the approval boundary was asked for, and what it did.

    The boundary is the most safety-critical part of the application, and
    it was invisible: the owner could not see what had been allowed, what
    had been refused, or what an emergency stop had thrown away. These
    records make that visible, and they are kept in memory only: they
    never leave the machine and they are not written to the history.
    """

    kind: str
    target: str
    outcome: str
    detail: str = ''

    def as_dict(self) -> dict:
        return {'kind': self.kind, 'target': self.target,
                'outcome': self.outcome, 'detail': self.detail}


#: How many decisions are kept.
MAX_DECISIONS = 200


class Policy:
    def __init__(self, mode=ApprovalMode.ASK):
        self._lock = RLock()
        self._mode = ApprovalMode.from_setting(mode)
        self._generation = 0
        self._stopped = False
        self._grants = {}
        self._decisions = []
        #: How many pending approvals an emergency stop threw away.
        self.invalidated = 0

    @property
    def stopped(self):
        with self._lock:
            return self._stopped

    @property
    def mode(self):
        with self._lock:
            return self._mode

    def set_mode(self, mode):
        with self._lock:
            self._mode = ApprovalMode.from_setting(mode)

    def requires_confirmation(self, action):
        with self._lock:
            if action.approval_scope is ApprovalScope.ROUTINE:
                return self._mode is ApprovalMode.ASK
            if action.approval_scope is ApprovalScope.LOCAL_WRITE:
                return self._mode is not ApprovalMode.FULL
            return True

    def ticket(self):
        with self._lock:
            if self._stopped:
                raise Stopped('Emergency stop is active. Resume explicitly.')
            return self._generation

    def check(self, ticket):
        with self._lock:
            if self._stopped or ticket != self._generation:
                raise Stopped('Operation cancelled by emergency stop.')

    def run_if_current(self, ticket, operation):
        with self._lock:
            self.check(ticket)
            return operation()

    def stop(self):
        with self._lock:
            self._stopped = True
            self._generation += 1
            # Every approval that was waiting is thrown away, and the
            # owner is told how many there were.
            self.invalidated += len(self._grants)
            for grant in list(self._grants.values()):
                self._record(grant[1].kind, grant[1].target, 'stopped',
                             'an emergency stop threw this approval away')
            self._grants.clear()

    def _record(self, kind, target, outcome, detail=''):
        """Keep one decision, and forget the oldest when there are too many."""
        self._decisions.append(Decision(kind=kind, target=target,
                                        outcome=outcome, detail=detail))
        if len(self._decisions) > MAX_DECISIONS:
            del self._decisions[:-MAX_DECISIONS]

    def decisions(self) -> list:
        """What the boundary was asked for, newest last."""
        with self._lock:
            return list(self._decisions)

    def decision_counts(self) -> dict:
        """How many of each outcome there are."""
        with self._lock:
            counts = {}
            for decision in self._decisions:
                counts[decision.outcome] = counts.get(decision.outcome, 0) + 1
            return counts

    def summary(self) -> str:
        """The boundary, in words the owner can read."""
        counts = self.decision_counts()
        allowed = counts.get('allowed', 0)
        refused = counts.get('refused', 0)
        stopped = counts.get('stopped', 0)
        return (
            f'{allowed} action(s) allowed, {refused} refused, '
            f'{stopped} thrown away by an emergency stop. '
            f'{self.invalidated} pending approval(s) have been invalidated in total. '
            'An approval is used once and cannot be replayed.'
        )

    def resume(self):
        with self._lock:
            self._stopped = False

    def approve(self, action, confirm, *, auto_approve=True):
        with self._lock:
            ticket = self.ticket()
            if auto_approve and not self.requires_confirmation(action):
                token = uuid.uuid4().hex
                self._grants[token] = (ticket, action, self._mode)
                return token
        if not confirm(action):
            with self._lock:
                self._record(action.kind, action.target, 'refused',
                             'the owner declined it')
            raise Denied('Action declined.')
        with self._lock:
            self.check(ticket)
            token = uuid.uuid4().hex
            self._grants[token] = (ticket, action, None)
            return token

    def execute(self, action, token, operation):
        # Serialize short mutations with stop: nothing new starts after stop.
        with self._lock:
            grant = self._grants.pop(token, None)
            if grant is None or grant[1] != action:
                # A grant that an emergency stop threw away is not a
                # refusal: the owner never said no.
                outcome = 'stopped' if self._stopped else 'refused'
                detail = ('an emergency stop threw this approval away'
                          if self._stopped
                          else 'the one-use approval was missing or did not match')
                self._record(action.kind, action.target, outcome, detail)
                raise Denied('Missing or mismatched one-use approval.')
            try:
                self.check(grant[0])
            except Stopped:
                self._record(action.kind, action.target, 'stopped',
                             'an emergency stop was active')
                raise
            automatic_mode = grant[2]
            if automatic_mode is not None and self.requires_confirmation(action):
                self._record(action.kind, action.target, 'refused',
                             'the approval mode changed before execution')
                raise Denied('Approval mode changed. Request the action again.')
            detail = f'automatically approved in {automatic_mode.value} mode' if automatic_mode else ''
            self._record(action.kind, action.target, 'allowed', detail)
            return operation()
