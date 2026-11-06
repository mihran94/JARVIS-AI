"""Windows Job Object limit planning; no process is launched by this module.

A Job Object is a resource-control primitive, NOT an isolation sandbox.
Actual Win32 process creation/assignment is deliberately not implemented.
"""
from dataclasses import dataclass
import os
from .resource_policy import ResourcePolicy, IsolationUnavailable

JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


@dataclass(frozen=True)
class JobLimits:
    flags: int
    memory_bytes: int
    active_process_limit: int
    timeout_seconds: float
    max_output_bytes: int


def compile_job_limits(policy: ResourcePolicy) -> JobLimits:
    """Translate validated policy to Job Object values without OS side effects."""
    if not isinstance(policy, ResourcePolicy):
        raise TypeError('policy must be ResourcePolicy')
    return JobLimits(
        flags=(JOB_OBJECT_LIMIT_ACTIVE_PROCESS |
               JOB_OBJECT_LIMIT_PROCESS_MEMORY |
               JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE),
        memory_bytes=policy.memory_mb * 1024 * 1024,
        active_process_limit=policy.max_processes,
        timeout_seconds=policy.timeout_seconds,
        max_output_bytes=policy.max_output_bytes,
    )


def require_windows_job_host(*, platform: str | None = None) -> None:
    """Fail closed on unsupported hosts; capability check, not VM attestation."""
    host = os.name if platform is None else platform
    if host != 'nt':
        raise IsolationUnavailable('Windows Job Objects require a Windows host')


def verify_execution_preconditions(*, policy: ResourcePolicy,
                                   isolation_backend: str,
                                   isolation_verified: bool,
                                   approval_valid: bool,
                                   windows_host: bool) -> JobLimits:
    """Policy-only gate; a caller must independently attest isolation/approval.

    This does NOT perform a process launch or verify the truth of caller claims.
    """
    from .resource_policy import require_isolated_backend
    if approval_valid is not True:
        raise PermissionError('Explicit valid approval required')
    require_isolated_backend(backend=isolation_backend, verified=isolation_verified)
    if windows_host is not True:
        raise IsolationUnavailable('Windows resource controller unavailable')
    if policy.network_allowed:
        raise IsolationUnavailable('Network policy must be enforced by VM, not Job Objects')
    return compile_job_limits(policy)
