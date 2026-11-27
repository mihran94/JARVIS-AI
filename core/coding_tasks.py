"""Saved coding tasks: what was asked, which provider was doing it, how far it got.

WHY THIS IS SAVED
    A coding provider can stop halfway through. A key can be rate limited, a
    quota can run out, the network can drop, the window can be closed. When
    that happens the task must not be lost, because the work that was already
    done is sitting in a worktree and it should not have to be asked for
    again.

    So the task is written to the task history before the provider is called,
    and it is updated as the work goes. A task that stopped for a reason that
    can pass — a rate limit, a quota, a network failure — is left in the
    state `waiting`, with the reason, so it can be resumed.

THE RULE ABOUT SWITCHING PROVIDER
    When the selected coding provider cannot do the work, JARVIS does not
    quietly use the other one. The task is saved, the owner is told what
    happened, and the switch to the other coding provider is an action the
    owner approves, through the same approval gate as every other action.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json

from core.development import Improvement

KIND = 'coding_task'

#: The states a task can be in.
PENDING = 'pending'
RUNNING = 'running'
WAITING = 'waiting'
COMPLETED = 'completed'
FAILED = 'failed'
REJECTED = 'rejected'
READY = 'ready'
INTERRUPTED = 'interrupted'

#: The states from which a task can be resumed.
RESUMABLE = (PENDING, RUNNING, WAITING, FAILED, INTERRUPTED)


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def create(store, goal: str, provider: str) -> Improvement:
    """Save a new task before any work starts."""
    ident = store.task(KIND, '')
    improvement = Improvement(ident=ident, goal=goal, provider=provider, state=PENDING,
                              prepared_at=_now())
    store.finish(ident, PENDING, json.dumps(improvement.as_dict()))
    return improvement


def save(store, improvement: Improvement) -> Improvement:
    """Write the task back, keeping its history row in step."""
    updated = Improvement(**{**improvement.as_dict(), 'prepared_at': improvement.prepared_at or _now()})
    store.finish(updated.ident, updated.state, json.dumps(updated.as_dict()))
    return updated


def set_state(store, improvement: Improvement, state: str, reason: str = '') -> Improvement:
    """Move the task to another state and keep the reason."""
    return save(store, Improvement(**{
        **improvement.as_dict(), 'state': state, 'reason': reason or improvement.reason,
    }))


def load(store, ident: str) -> Improvement | None:
    """One task, or None when the history no longer has it."""
    for row in store.tasks():
        if row.get('id') == ident and row.get('kind') == KIND:
            return _from_row(row)
    return None


def tasks(store) -> list[Improvement]:
    """Every saved coding task, newest first."""
    return [_from_row(row) for row in store.tasks() if row.get('kind') == KIND]


def prepared(store) -> list[Improvement]:
    """The tasks that are ready for the owner to review."""
    return [task for task in tasks(store) if task.state == READY]


def waiting(store) -> list[Improvement]:
    """The tasks that stopped for a reason that may pass."""
    return [task for task in tasks(store) if task.state == WAITING]


def resumable(store) -> list[Improvement]:
    """The tasks that can be picked up again."""
    return [task for task in tasks(store) if task.state in RESUMABLE]


def _from_row(row: dict) -> Improvement:
    try:
        data = json.loads(row.get('detail') or '{}')
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return Improvement.from_dict({**data, 'ident': str(row.get('id', '')),
                                  'state': str(row.get('status') or data.get('state') or PENDING)})


def describe_failure(diagnosis) -> str:
    """One line about a provider failure that stopped a coding task.

    The diagnosis already knows what went wrong and what to do about it; this
    only says what happens to the task now.
    """
    if diagnosis is None:
        return 'The coding provider stopped. The task was saved and can be resumed.'
    return f'{diagnosis.message} The task was saved and can be resumed.'
