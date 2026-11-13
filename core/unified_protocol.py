"""Cross-device JARVIS BLUE envelope v1 (transport independent).

This module validates message shape only. Authentication, encryption, device
pairing, replay protection and network transport MUST be implemented separately.
No action is executed by this module.
"""
import json
import re
from uuid import UUID

PROTOCOL = "jarvis-blue/1"
KINDS = frozenset({"hello", "status", "chat_request", "chat_response", "action_proposal", "action_result"})
_DEVICE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ProtocolError(ValueError):
    pass


def validate_envelope(value):
    if not isinstance(value, dict):
        raise ProtocolError("Envelope must be an object")
    if set(value) != {"protocol", "id", "device_id", "kind", "payload"}:
        raise ProtocolError("Unexpected or missing envelope fields")
    if value["protocol"] != PROTOCOL or value["kind"] not in KINDS:
        raise ProtocolError("Unsupported protocol or message kind")
    try:
        UUID(value["id"])
    except (ValueError, TypeError, AttributeError):
        raise ProtocolError("Invalid message id") from None
    if not isinstance(value["device_id"], str) or not _DEVICE.fullmatch(value["device_id"]):
        raise ProtocolError("Invalid device id")
    if not isinstance(value["payload"], dict):
        raise ProtocolError("Payload must be an object")
    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 65536:
        raise ProtocolError("Envelope too large")
    return value


def decode_envelope(raw):
    if not isinstance(raw, (str, bytes)) or len(raw) > 65536:
        raise ProtocolError("Invalid message encoding or size")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ProtocolError("Invalid JSON") from None
    return validate_envelope(value)
