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
        data = status_provider()
        if not isinstance(data, dict) or set(data) - {"ready", "stopped", "version"}:
            raise CapabilityUnavailable("Status provider returned unexpected fields")
        if any(type(value) not in (bool, str, int) for value in data.values()):
            raise CapabilityUnavailable("Invalid status field type")
        return {"version": 1, "request_id": request.request_id,
                "capability": request.capability, "data": data}
    if request.capability == "tasks.read":
        data = tasks_provider()
        if not isinstance(data, list) or len(data) > 100:
            raise CapabilityUnavailable("Invalid task summary list")
        if any(not isinstance(item, dict) or set(item) != {"status"} or
               not isinstance(item["status"], str) or len(item["status"]) > 32
               for item in data):
            raise CapabilityUnavailable("Task summaries must contain status only")
        return {"version": 1, "request_id": request.request_id,
                "capability": request.capability, "data": data}
    raise CapabilityUnavailable("Remote chat and automation are not enabled")
