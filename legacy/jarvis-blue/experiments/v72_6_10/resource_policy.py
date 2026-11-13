"""Validated resource budgets and explicit Windows isolation capability checks.

This module does NOT enforce budgets; enforcement belongs to an OS/VM backend.
"""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ResourcePolicy:
    timeout_seconds: float = 30.0
    memory_mb: int = 256
    max_processes: int = 1
    max_output_bytes: int = 4096
    network_allowed: bool = False

    def __post_init__(self) -> None:
        if not 0 < self.timeout_seconds <= 3600:
            raise ValueError('timeout_seconds must be in (0, 3600]')
        if not 32 <= self.memory_mb <= 32768:
            raise ValueError('memory_mb must be in [32, 32768]')
        if not 1 <= self.max_processes <= 64:
            raise ValueError('max_processes must be in [1, 64]')
        if not 1 <= self.max_output_bytes <= 1_000_000:
            raise ValueError('max_output_bytes must be in [1, 1000000]')
        if type(self.network_allowed) is not bool:
            raise ValueError('network_allowed must be boolean')


class IsolationUnavailable(RuntimeError):
    pass


def require_isolated_backend(*, backend: str, verified: bool) -> None:
    """Fail closed unless caller has independently verified an isolation backend.

    `verified` must come from an actual VM/container attestation, not AI text.
    """
    if backend not in {'windows_sandbox', 'isolated_vm'} or verified is not True:
        raise IsolationUnavailable('Verified OS isolation is required for untrusted code')


def windows_job_objects_available() -> bool:
    """Capability hint only: Windows Job Objects alone are not a sandbox."""
    return os.name == 'nt'
