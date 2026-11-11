"""Bridge job records shared with the Android client.

The wire names and values are fixed by the Kotlin client in
`core/model/WindowsBridge.kt` (jarvis-blue-android):

- kinds: PYTHON_PROJECT, AFTER_EFFECTS_RENDER, CODE_REVIEW, DOCUMENT_ACCESS,
  WORKFLOW, CUSTOM
- states: QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED, REJECTED

A job submitted over the bridge is never executed by the bridge. It is recorded
as QUEUED and, when the request asked for approval, it stays QUEUED until the
desktop owner approves it in the Qt interface. That keeps the existing
per-action confirmation boundary in force for remote requests too.
"""
from dataclasses import dataclass, field
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
    requires_approval: bool = False

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
        }


class JobStore:
    """In-memory job records with an explicit state machine."""

    def __init__(self, *, now=time.time):
        self._now = now
        self._jobs: dict[str, BridgeJob] = {}
        self._lock = threading.RLock()

    def submit(self, kind: str, title: str, payload: str, require_approval: bool) -> BridgeJob:
        """Record a submitted job. It is never started by the bridge."""
        if kind not in JOB_KINDS:
            raise JobError('Unknown job kind.')
        if not isinstance(title, str) or not title.strip():
            raise JobError('A job title is required.')
        if not isinstance(payload, str):
            raise JobError('The job payload must be a JSON string.')
        if type(require_approval) is not bool:
            raise JobError('Approval must be an explicit boolean.')
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
                requires_approval=require_approval,
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

    def approve(self, job_id: str) -> BridgeJob:
        """Owner approval moves a job out of the approval wait."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobError('Unknown job.')
            if job.state in TERMINAL_STATES:
                raise JobError('That job has already finished.')
            job = self._replace(job, state='RUNNING')
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
            self._jobs[job_id] = self._replace(job, state='CANCELLED')
            return True

    def _replace(self, job: BridgeJob, **changes) -> BridgeJob:
        data = {
            'id': job.id,
            'kind': job.kind,
            'title': job.title,
            'state': job.state,
            'progress': job.progress,
            'created_at': job.created_at,
            'updated_at': int(self._now() * 1000),
            'logs': job.logs,
            'outputs': job.outputs,
            'error': job.error,
            'requires_approval': job.requires_approval,
        }
        data.update(changes)
        return BridgeJob(**data)
