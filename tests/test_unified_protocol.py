import json
import unittest
from jarvis_unified.protocol import parse_request, ProtocolError, MAX_MESSAGE_BYTES


def request(**overrides):
    obj = {"version": 1, "request_id": "request_1234", "capability": "status.read", "payload": {}}
    obj.update(overrides)
    return json.dumps(obj).encode()


class ProtocolTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_request(request()).capability, "status.read")

    def test_invalid_version(self):
        with self.assertRaises(ProtocolError):
            parse_request(request(version=True))

    def test_unsupported_capability(self):
        with self.assertRaises(ProtocolError):
            parse_request(request(capability="shell.exec"))

    def test_invalid_request_id(self):
        with self.assertRaises(ProtocolError):
            parse_request(request(request_id="../etc"))

    def test_payload_must_be_object(self):
        with self.assertRaises(ProtocolError):
            parse_request(request(payload=[]))

    def test_extra_field_rejected(self):
        with self.assertRaises(ProtocolError):
            parse_request(request(secret="x"))

    def test_message_size_limit(self):
        with self.assertRaises(ProtocolError):
            parse_request(b"x" * (MAX_MESSAGE_BYTES + 1))

    def test_invalid_json(self):
        with self.assertRaises(ProtocolError):
            parse_request(b"{")
