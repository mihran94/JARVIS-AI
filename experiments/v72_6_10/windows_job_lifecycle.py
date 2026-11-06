"""V72.6.7 Windows Job Object lifecycle *model*, not a process launcher.

This state machine is for testing order of privileged Win32 operations.
It does not attest VM isolation, issue approvals, or execute scripts.
"""
from dataclasses import dataclass, replace
from enum import Enum


class Phase(str, Enum):
    NEW = 'new'
    SUSPENDED = 'suspended'
    ASSIGNED = 'assigned'
    LIMITS_APPLIED = 'limits_applied'
    RUNNING = 'running'
    CLOSED = 'closed'
    FAILED = 'failed'


class UnsafeTransition(RuntimeError):
    pass


@dataclass(frozen=True)
class JobLifecycle:
    phase: Phase = Phase.NEW
    process_id: int | None = None
    job_handle_owned: bool = False
    approval_consumed: bool = False
    events: tuple[str, ...] = ()

    def advance(self, event: str, *, process_id: int | None = None) -> 'JobLifecycle':
        steps = {
            ('new', 'created_suspended'): Phase.SUSPENDED,
            ('suspended', 'assigned_to_job'): Phase.ASSIGNED,
            ('assigned', 'limits_applied'): Phase.LIMITS_APPLIED,
            ('limits_applied', 'resumed'): Phase.RUNNING,
        }
        if event == 'fail':
            if self.phase in (Phase.CLOSED, Phase.FAILED):
                raise UnsafeTransition('terminal state')
            return replace(self, phase=Phase.FAILED, events=self.events + (event,))
        if event == 'close_job':
            if self.phase in (Phase.CLOSED, Phase.NEW):
                raise UnsafeTransition('job not open')
            return replace(self, phase=Phase.CLOSED, job_handle_owned=False,
                           events=self.events + (event,))
        target = steps.get((self.phase.value, event))
        if target is None:
            raise UnsafeTransition(f'{event} invalid in {self.phase.value}')
        if event == 'created_suspended':
            if not isinstance(process_id, int) or isinstance(process_id, bool) or process_id <= 0:
                raise UnsafeTransition('valid process ID required')
            return replace(self, phase=target, process_id=process_id,
                           job_handle_owned=True, approval_consumed=True,
                           events=self.events + (event,))
        if not self.job_handle_owned or not self.approval_consumed:
            raise UnsafeTransition('job ownership and approval required')
        return replace(self, phase=target, events=self.events + (event,))

    @property
    def may_resume(self) -> bool:
        return (self.phase == Phase.LIMITS_APPLIED and self.job_handle_owned
                and self.approval_consumed)
