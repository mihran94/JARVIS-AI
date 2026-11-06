import unittest
from dataclasses import replace
from experiments.v72_6_10.resource_policy import (
    ResourcePolicy, IsolationUnavailable, require_isolated_backend,
    windows_job_objects_available,
)


class ResourcePolicyTests(unittest.TestCase):
    def test_defaults_are_local_first(self):
        p = ResourcePolicy()
        self.assertFalse(p.network_allowed)
        self.assertEqual(p.max_processes, 1)

    def test_valid_custom_limits(self):
        p = ResourcePolicy(timeout_seconds=2, memory_mb=128, max_processes=2)
        self.assertEqual(p.memory_mb, 128)

    def test_reject_invalid_limits(self):
        cases = [('timeout_seconds', 0), ('timeout_seconds', 3601),
                 ('memory_mb', 31), ('memory_mb', 32769),
                 ('max_processes', 0), ('max_processes', 65),
                 ('max_output_bytes', 0), ('max_output_bytes', 1000001),
                 ('network_allowed', 'false')]
        for name, value in cases:
            with self.subTest(name=name, value=value):
                with self.assertRaises(ValueError):
                    replace(ResourcePolicy(), **{name: value})

    def test_unverified_isolation_rejected(self):
        for backend in ('windows_sandbox', 'isolated_vm', 'subprocess', ''):
            with self.subTest(backend=backend):
                with self.assertRaises(IsolationUnavailable):
                    require_isolated_backend(backend=backend, verified=False)

    def test_subprocess_never_qualifies(self):
        with self.assertRaises(IsolationUnavailable):
            require_isolated_backend(backend='subprocess', verified=True)

    def test_verified_vm_accepted(self):
        require_isolated_backend(backend='isolated_vm', verified=True)

    def test_capability_is_boolean(self):
        self.assertIsInstance(windows_job_objects_available(), bool)


if __name__ == '__main__':
    unittest.main()
