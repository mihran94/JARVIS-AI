"""Fail-closed Windows execution readiness checks. No process execution.

This module is NOT sandbox attestation and cannot make host execution safe.
"""
from dataclasses import dataclass
import os
from .resource_policy import ResourcePolicy, IsolationUnavailable
from .windows_job_policy import JobLimits, compile_job_limits


@dataclass(frozen=True)
class WindowsCapabilities:
    is_windows: bool
    in_dedicated_vm: bool
    vm_isolation_attested: bool
    network_disabled: bool
    host_shares_disabled: bool
    job_objects_supported: bool
    suspended_launch_supported: bool
    kill_on_close_supported: bool


@dataclass(frozen=True)
class ExecutionPlan:
    limits: JobLimits
    backend: str
    requires_single_use_approval: bool = True
    executable: bool = False  # planning output must never authorize execution


def build_execution_plan(policy: ResourcePolicy, capabilities: WindowsCapabilities,
                         *, approval_valid: bool) -> ExecutionPlan:
    """Reject missing controls; returning a plan NEVER launches or approves code."""
    if not isinstance(policy, ResourcePolicy):
        raise TypeError('policy must be ResourcePolicy')
    if not isinstance(capabilities, WindowsCapabilities):
        raise TypeError('capabilities must be WindowsCapabilities')
    if approval_valid is not True:
        raise PermissionError('Explicit single-use approval required')
    if policy.network_allowed:
        raise IsolationUnavailable('Network-enabled execution is not supported')
    required = (
        'is_windows', 'in_dedicated_vm', 'vm_isolation_attested',
        'network_disabled', 'host_shares_disabled', 'job_objects_supported',
        'suspended_launch_supported', 'kill_on_close_supported',
    )
    missing = [name for name in required if getattr(capabilities, name) is not True]
    if missing:
        raise IsolationUnavailable('Missing verified controls: ' + ', '.join(missing))
    return ExecutionPlan(limits=compile_job_limits(policy), backend='windows-vm-job-object')


def observed_host_capabilities() -> WindowsCapabilities:
    """Only report independently observable OS; never infer VM security."""
    return WindowsCapabilities(
        is_windows=os.name == 'nt',
        in_dedicated_vm=False, vm_isolation_attested=False,
        network_disabled=False, host_shares_disabled=False,
        job_objects_supported=False, suspended_launch_supported=False,
        kill_on_close_supported=False,
    )
