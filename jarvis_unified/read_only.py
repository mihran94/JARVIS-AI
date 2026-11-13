"""Safe adapter between the existing shared protocol and Windows state.

No HTTP server, pairing, or authentication is provided here. A future authenticated
transport may invoke this dispatcher only after device authorization and replay
checks. Mutating capabilities remain disabled.
"""
from jarvis_unified.protocol import parse_request


class CapabilityUnavailable(PermissionError):
    pass


def dispatch_read_only(raw, *, status_provider, tasks_provider, stopped=False):
    """Handle strictly read-only requests; do not expose private task details by default."""
    request = parse_request(raw)
    if stopped:
        raise CapabilityUnavailable("Emergency stop active")
    if request.payload:
        raise CapabilityUnavailable("Read-only requests must have empty payload")
    if request.capability == "status.read":
        return {"version": 1, "request_id": request.request_id,
                "capability": request.capability, "data": status_provider()}
    if request.capability == "tasks.read":
        return {"version": 1, "request_id": request.request_id,
                "capability": request.capability, "data": tasks_provider()}
    raise CapabilityUnavailable("Remote chat and automation are not enabled")
