"""Fail-closed boundary for remotely requested coding commands.

Not a sandbox. Execution requires a separately verified OS isolation mechanism.
"""
from dataclasses import dataclass


class ExecutionDenied(PermissionError):
    pass


@dataclass(frozen=True)
class ExecutionAuthorization:
    local_approval: bool = False
    paired_device_authenticated: bool = False
    capability_granted: bool = False
    isolation_verified: bool = False
    emergency_stopped: bool = False


def require_remote_execution_authorization(auth: ExecutionAuthorization) -> None:
    if auth.emergency_stopped:
        raise ExecutionDenied('emergency stop active')
    if not auth.paired_device_authenticated:
        raise ExecutionDenied('device authentication required')
    if not auth.capability_granted:
        raise ExecutionDenied('execution capability not granted')
    if not auth.local_approval:
        raise ExecutionDenied('local user approval required')
    if not auth.isolation_verified:
        raise ExecutionDenied('OS isolation not verified; command execution disabled')
