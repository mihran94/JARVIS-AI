import unittest
from dataclasses import replace
from unittest.mock import patch
from experiments.v72_6_10.resource_policy import ResourcePolicy, IsolationUnavailable
from experiments.v72_6_10.windows_execution_preflight import (
    WindowsCapabilities, build_execution_plan, observed_host_capabilities,
)


def secure_caps():
    return WindowsCapabilities(*(True for _ in range(8)))


class PreflightTests(unittest.TestCase):
    def test_complete_plan_still_not_executable(self):
        plan = build_execution_plan(ResourcePolicy(), secure_caps(), approval_valid=True)
        self.assertFalse(plan.executable)
        self.assertTrue(plan.requires_single_use_approval)
        self.assertEqual(plan.limits.memory_bytes, 256 * 1024 * 1024)

    def test_missing_approval(self):
        with self.assertRaises(PermissionError):
            build_execution_plan(ResourcePolicy(), secure_caps(), approval_valid=False)

    def test_network_policy_rejected(self):
        with self.assertRaises(IsolationUnavailable):
            build_execution_plan(ResourcePolicy(network_allowed=True), secure_caps(), approval_valid=True)

    def test_each_control_fails_closed(self):
        for field in secure_caps().__dataclass_fields__:
            with self.subTest(field=field):
                with self.assertRaises(IsolationUnavailable):
                    build_execution_plan(ResourcePolicy(), replace(secure_caps(), **{field: False}), approval_valid=True)

    def test_non_boolean_capability_rejected(self):
        with self.assertRaises(IsolationUnavailable):
            build_execution_plan(ResourcePolicy(), replace(secure_caps(), vm_isolation_attested=1), approval_valid=True)

    def test_observation_never_attests_vm(self):
        with patch('experiments.v72_6_10.windows_execution_preflight.os.name', 'nt'):
            caps = observed_host_capabilities()
        self.assertTrue(caps.is_windows)
        self.assertFalse(caps.vm_isolation_attested)
        self.assertFalse(caps.job_objects_supported)

    def test_invalid_types(self):
        with self.assertRaises(TypeError):
            build_execution_plan(None, secure_caps(), approval_valid=True)
        with self.assertRaises(TypeError):
            build_execution_plan(ResourcePolicy(), None, approval_valid=True)


if __name__ == '__main__':
    unittest.main()
