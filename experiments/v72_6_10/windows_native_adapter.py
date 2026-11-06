"""V72.6.8 fail-closed native adapter boundary; deliberately no Win32 execution.

The real Windows backend must supply independent VM attestation and safe handle
ownership before this interface can be implemented. This module never launches.
"""
from dataclasses import dataclass
from enum import Enum
from .windows_job_lifecycle import JobLifecycle, Phase
from .windows_execution_preflight import ExecutionPlan

class Operation(str, Enum):
    CREATE_SUSPENDED = 'CreateProcessW(CREATE_SUSPENDED)'
    ASSIGN_JOB = 'AssignProcessToJobObject'
    SET_LIMITS = 'SetInformationJobObject'
    RESUME = 'ResumeThread'
    CLOSE_JOB = 'CloseHandle(job)'

@dataclass(frozen=True)
class NativeStep:
    operation: Operation
    required_phase: Phase
    next_phase: Phase

STEPS = (
    NativeStep(Operation.CREATE_SUSPENDED, Phase.NEW, Phase.SUSPENDED),
    NativeStep(Operation.ASSIGN_JOB, Phase.SUSPENDED, Phase.ASSIGNED),
    NativeStep(Operation.SET_LIMITS, Phase.ASSIGNED, Phase.LIMITS_APPLIED),
    NativeStep(Operation.RESUME, Phase.LIMITS_APPLIED, Phase.RUNNING),
    NativeStep(Operation.CLOSE_JOB, Phase.RUNNING, Phase.CLOSED),
)

class NativeExecutionUnavailable(RuntimeError):
    pass

def describe_native_sequence(plan: ExecutionPlan) -> tuple[NativeStep, ...]:
    """Documentation-only sequence, never an authorization or launch."""
    if not isinstance(plan, ExecutionPlan):
        raise TypeError('ExecutionPlan required')
    if plan.executable is not False or plan.requires_single_use_approval is not True:
        raise NativeExecutionUnavailable('Unsafe or modified execution plan')
    if plan.backend != 'windows-vm-job-object':
        raise NativeExecutionUnavailable('Unsupported backend')
    return STEPS

def execute_native(*args, **kwargs):
    """Fail closed until actual VM-attested Win32 implementation is audited."""
    raise NativeExecutionUnavailable('Native execution not implemented; no process launched')
