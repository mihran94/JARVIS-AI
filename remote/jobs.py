"""Bridge job records shared with the Android client.

The wire names and values are fixed by the Kotlin client in
`core/model/WindowsBridge.kt` (jarvis-blue-android):

- kinds: PYTHON_PROJECT, AFTER_EFFECTS_RENDER, CODE_REVIEW, DOCUMENT_ACCESS,
  WORKFLOW, CUSTOM
- states: QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED, REJECTED

The bridge records submitted jobs as QUEUED. Only the desktop approval
path can dispatch an approved action and record its verified result.
"""
from dataclasses import dataclass, field, replace
import json
import threading
import time
import uuid

JOB_KINDS = (
    'PYTHON_PROJECT',
    'AFTER_EFFECTS_RENDER',
    'CODE_REVIEW',
    'DOCUMENT_ACCESS',
    'WORKFLOW',
    'CUSTOM',
)

JOB_STATES = (
    'QUEUED',
    'RUNNING',
    'SUCCEEDED',
    'FAILED',
    'CANCELLED',
    'REJECTED',
)

DISK_SPACE_ACTION = 'check_disk_space'
OPEN_APP_ACTION = 'open_installed_app'
#: The phone asks the desktop to back up the history.
HISTORY_BACKUP_ACTION = 'backup_history'
#: The phone asks the desktop to restore a backup it named.
HISTORY_RESTORE_ACTION = 'restore_history'
#: The actions a phone may ask for.
SUPPORTED_ACTIONS = (DISK_SPACE_ACTION, HISTORY_BACKUP_ACTION, HISTORY_RESTORE_ACTION, OPEN_APP_ACTION)


def operation_kind(operation) -> str:
    """The action of an operation, without any argument it carries.

    The restore names the backup it wants, and that name travels with
    the operation rather than as free text, because a job record keeps
    no phone text at all.
    """
    if not isinstance(operation, str):
        return ''
    return operation.split(':', 1)[0]

#: States from which a job can no longer change.
TERMINAL_STATES = ('SUCCEEDED', 'FAILED', 'CANCELLED', 'REJECTED')


class JobError(RuntimeError):
    """The requested job change is not allowed."""


@dataclass(frozen=True)
class BridgeJob:
    """A job record in the exact shape the Android client parses."""

    id: str
    kind: str
    title: str
    state: str = 'QUEUED'
    progress: float = 0.0
    created_at: int = 0
    updated_at: int = 0
    logs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    error: str | None = None
    requires_approval: bool = True
    operation: str | None = None
    peer_id: str | None = None
    started_at: int | None = None
    finished_at: int | None = None

    def to_json(self) -> dict:
        """The snake_case payload the Android client reads."""
        return {
            'id': self.id,
            'kind': self.kind,
            'title': self.title,
            'state': self.state,
            'progress': self.progress,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'logs': list(self.logs),
            'outputs': list(self.outputs),
            'error': self.error,
            'requires_approval': self.requires_approval,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
        }


class JobStore:
    """In-memory job records with an explicit state machine."""

    def __init__(self, *, now=time.time):
        self._now = now
        self._jobs: dict[str, BridgeJob] = {}
        self._lock = threading.RLock()

    def submit(self, kind: str, title: str, payload: str, require_approval: bool,
               *, peer_id: str | None = None) -> BridgeJob:
        """Record a submitted job. It is never started by the bridge."""
        if kind not in JOB_KINDS:
            raise JobError('Unknown job kind.')
        if not isinstance(title, str) or not title.strip():
            raise JobError('A job title is required.')
        if not isinstance(payload, str):
            raise JobError('The job payload must be a JSON string.')
        if type(require_approval) is not bool:
            raise JobError('Approval must be an explicit boolean.')
        # Retain only the validated operation, never arbitrary phone text.
        operation = None
        if kind == 'CUSTOM' and len(payload) <= 256:
            try:
                data = json.loads(payload)
            except ValueError:
                data = None
            if isinstance(data, dict) and data.get('action') in SUPPORTED_ACTIONS:
                operation = data['action']
                if operation == OPEN_APP_ACTION:
                    name = data.get('app')
                    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 80
                            or not name.isprintable() or any(c in name for c in '/\\:')):
                        operation = None
                    else:
                        operation = f'{OPEN_APP_ACTION}:{name.strip()}'
                        title = f'Open {name.strip()}'
                if operation == HISTORY_RESTORE_ACTION:
                    name = data.get('backup', '')
                    # Only a plain file name is accepted, so a phone can
                    # never point the restore at a path of its choosing.
                    if (not isinstance(name, str) or not name
                            or '/' in name or '\\' in name or '..' in name
                            or not name.endswith('.jarvisbak')):
                        operation = None
                    else:
                        operation = f'{HISTORY_RESTORE_ACTION}:{name}'
        moment = int(self._now() * 1000)
        with self._lock:
            job = BridgeJob(
                id=uuid.uuid4().hex,
                kind=kind,
                title=title.strip(),
                state='QUEUED',
                created_at=moment,
                updated_at=moment,
                logs=[],
                outputs=[],
                error=None,
                operation=operation,
                peer_id=peer_id,
            )
            self._jobs[job.id] = job
            return job

    def get(self, job_id: str) -> BridgeJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[BridgeJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at)

    def counts(self) -> tuple[int, int]:
        """Return the queued and running counts reported by the status call."""
        with self._lock:
            queued = sum(1 for job in self._jobs.values() if job.state == 'QUEUED')
            running = sum(1 for job in self._jobs.values() if job.state == 'RUNNING')
            return queued, running

    def start(self, job_id: str) -> BridgeJob:
        """Claim an approved job immediately before calling its executor."""
        with self._lock:
            job = self._jobs.get(job_id)
            if (job is None or job.state != 'QUEUED'
                    or operation_kind(job.operation) not in SUPPORTED_ACTIONS):
                raise JobError('The job is no longer queued or has no supported action.')
            job = self._replace(job, state='RUNNING', requires_approval=False,
                                started_at=int(self._now() * 1000),
                                logs=[f'Started {job.operation}.'])
            self._jobs[job_id] = job
            return job

    def finish(self, job_id: str, *, result: str | None = None,
               error: str | None = None) -> BridgeJob:
        """Record verified output, preserving cancellation if it arrived during execution."""
        if bool(result) == bool(error):
            raise ValueError('Provide either a verified result or an error.')
        with self._lock:
            job = self._jobs[job_id]
            if job.state == 'CANCELLED':
                return job
            if job.state != 'RUNNING':
                raise JobError('Only a running job can finish.')
            job = self._replace(
                job, state='FAILED' if error else 'SUCCEEDED',
                progress=0.0 if error else 1.0, error=error,
                logs=[*job.logs, 'Action failed.' if error else 'Action completed.'],
                outputs=[result] if result else [],
                finished_at=int(self._now() * 1000))
            self._jobs[job_id] = job
            return job

    def reject(self, job_id: str, reason: str) -> BridgeJob:
        with self._lock:
            job = self._jobs[job_id]
            if job.state != 'QUEUED':
                raise JobError('Only a queued job can be rejected.')
            job = self._replace(job, state='REJECTED', requires_approval=False,
                                error=reason, finished_at=int(self._now() * 1000))
            self._jobs[job_id] = job
            return job

    def cancel(self, job_id: str) -> bool:
        """Cancel a job that has not finished yet."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.state in TERMINAL_STATES:
                return False
            self._jobs[job_id] = self._replace(
                job, state='CANCELLED', requires_approval=False,
                finished_at=int(self._now() * 1000))
            return True

    def _replace(self, job: BridgeJob, **changes) -> BridgeJob:
        return replace(job, updated_at=int(self._now() * 1000), **changes)
