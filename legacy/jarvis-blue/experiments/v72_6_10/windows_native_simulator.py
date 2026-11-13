"""V72.6.9 dry-run native lifecycle verifier. NEVER launches OS processes.

A simulation does not provide Windows isolation or VM attestation.
"""
from dataclasses import dataclass
from .windows_native_adapter import describe_native_sequence, NativeExecutionUnavailable, Operation

@dataclass(frozen=True)
class SimulationResult:
    operations: tuple[str, ...]
    cleanup_attempted: bool
    completed: bool
    error: str | None = None

class RecordingBackend:
    """A recording-only backend; no arbitrary callbacks or Win32 handles."""
    def __init__(self, fail_on: Operation | None = None):
        if fail_on is not None and not isinstance(fail_on, Operation):
            raise TypeError('fail_on must be an Operation or None')
        self.fail_on = fail_on
        self.operations = []
        self.cleanup_attempted = False

    def record(self, operation: Operation):
        if not isinstance(operation, Operation):
            raise TypeError('Operation required')
        if operation is Operation.CLOSE_JOB:
            self.cleanup_attempted = True
        self.operations.append(operation.value)
        if operation == self.fail_on:
            raise RuntimeError('simulated operation failure')

def simulate_native_sequence(plan, fail_on: Operation | None = None) -> SimulationResult:
    """Validate contract and record simulated operations; never execute code."""
    steps = describe_native_sequence(plan)
    backend = RecordingBackend(fail_on)
    completed = False
    error = None
    try:
        for step in steps:
            backend.record(step.operation)
        completed = True
    except RuntimeError as exc:
        error = ('simulated cleanup failure' if backend.cleanup_attempted else str(exc))
    finally:
        if not backend.cleanup_attempted:
            try:
                backend.record(Operation.CLOSE_JOB)
            except RuntimeError:
                error = 'simulated cleanup failure'
                completed = False
    return SimulationResult(tuple(backend.operations), backend.cleanup_attempted, completed, error)
