"""V72.6.10 offline verification of recording-only native lifecycle traces.

Never launches code, validates OS security, or grants execution permission.
"""
from dataclasses import dataclass
from .windows_native_adapter import Operation
from .windows_native_simulator import SimulationResult

_ORDER = (Operation.CREATE_SUSPENDED.value, Operation.ASSIGN_JOB.value,
          Operation.SET_LIMITS.value, Operation.RESUME.value,
          Operation.CLOSE_JOB.value)

@dataclass(frozen=True)
class TraceAssessment:
    valid: bool
    reason: str
    resumed: bool
    cleanup_recorded: bool

def assess_trace(result: SimulationResult) -> TraceAssessment:
    if not isinstance(result, SimulationResult):
        raise TypeError("SimulationResult required")
    ops = result.operations
    if not isinstance(ops, tuple) or any(not isinstance(op, str) for op in ops):
        return TraceAssessment(False, "malformed trace", False, False)
    resumed = Operation.RESUME.value in ops
    cleaned = Operation.CLOSE_JOB.value in ops
    if not ops or len(ops) > len(_ORDER) or ops != _ORDER[:len(ops)]:
        if not (len(ops) >= 2 and ops[-1] == _ORDER[-1] and
                ops[:-1] == _ORDER[:len(ops)-1] and
                _ORDER[-1] not in ops[:-1]):
            return TraceAssessment(False, "out-of-order or duplicate operation", resumed, cleaned)
    if not cleaned or result.cleanup_attempted is not True:
        return TraceAssessment(False, "cleanup not recorded", resumed, cleaned)
    if result.completed is True:
        if ops != _ORDER or result.error is not None:
            return TraceAssessment(False, "inconsistent successful result", resumed, cleaned)
    elif result.completed is False:
        if not isinstance(result.error, str) or not result.error:
            return TraceAssessment(False, "failure missing error", resumed, cleaned)
    else:
        return TraceAssessment(False, "invalid completion flag", resumed, cleaned)
    return TraceAssessment(True, "recorded simulation trace is consistent", resumed, cleaned)
