"""Validation of untrusted requests arriving from a paired device.

This module does NOT authorize or execute actions. The Windows permission gate
must independently approve every sensitive action.
"""
import json
import re
from dataclasses import dataclass
from typing import Any

MAX_MESSAGE_BYTES = 16_384
_ID = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")
_CAPABILITIES = frozenset({"status.read", "tasks.read", "chat.send", "automation.request"})
VERSION = 1


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Request:
    request_id: str
    capability: str
    payload: dict[str, Any]


def parse_request(raw: bytes) -> Request:
    if not isinstance(raw, bytes) or len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("invalid message size")
    try:
        message = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("invalid JSON") from exc
    if not isinstance(message, dict) or set(message) != {"version", "request_id", "capability", "payload"}:
        raise ProtocolError("invalid envelope")
    if type(message["version"]) is not int or message["version"] != VERSION:
        raise ProtocolError("unsupported version")
    request_id = message["request_id"]
    if not isinstance(request_id, str) or not _ID.fullmatch(request_id):
        raise ProtocolError("invalid request ID")
    capability = message["capability"]
    if not isinstance(capability, str) or capability not in _CAPABILITIES:
        raise ProtocolError("unsupported capability")
    payload = message["payload"]
    if not isinstance(payload, dict):
        raise ProtocolError("invalid payload")
    return Request(request_id, capability, payload)
