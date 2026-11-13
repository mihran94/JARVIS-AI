"""Pure protocol adapter tests; no network or Windows automation."""
import json
import unittest
from jarvis_unified.read_only import dispatch_read_only, CapabilityUnavailable


def message(capability, payload=None):
    return json.dumps({"version": 1, "request_id": "request_1234",
                       "capability": capability, "payload": {} if payload is None else payload}).encode()


class ReadOnlyTests(unittest.TestCase):
    def test_status(self):
        result = dispatch_read_only(message("status.read"),
                                    status_provider=lambda: {"ready": True},
                                    tasks_provider=lambda: [])
        self.assertEqual(result["data"], {"ready": True})

    def test_tasks(self):
        result = dispatch_read_only(message("tasks.read"),
                                    status_provider=lambda: {},
                                    tasks_provider=lambda: [{"status": "waiting"}])
        self.assertEqual(result["data"][0]["status"], "waiting")

    def test_mutation_denied(self):
        for capability in ("chat.send", "automation.request"):
            with self.subTest(capability=capability):
                with self.assertRaises(CapabilityUnavailable):
                    dispatch_read_only(message(capability),
                                       status_provider=lambda: {}, tasks_provider=lambda: [])

    def test_mutating_requests_never_call_providers(self):
        calls = []
        def provider():
            calls.append('called')
            return {}
        for capability in ('chat.send', 'automation.request'):
            with self.assertRaises(CapabilityUnavailable):
                dispatch_read_only(message(capability),
                                   status_provider=provider, tasks_provider=provider)
        self.assertEqual(calls, [])

    def test_emergency_stop_never_calls_providers(self):
        calls = []
        def provider():
            calls.append('called')
            return {}
        with self.assertRaises(CapabilityUnavailable):
            dispatch_read_only(message('status.read'), stopped=True,
                               status_provider=provider, tasks_provider=provider)
        self.assertEqual(calls, [])

    def test_emergency_stop(self):
        with self.assertRaises(CapabilityUnavailable):
            dispatch_read_only(message("status.read"), stopped=True,
                               status_provider=lambda: {}, tasks_provider=lambda: [])

    def test_payload_rejected(self):
        with self.assertRaises(CapabilityUnavailable):
            dispatch_read_only(message("status.read", {"secret": "x"}),
                               status_provider=lambda: {}, tasks_provider=lambda: [])


if __name__ == "__main__":
    unittest.main()
