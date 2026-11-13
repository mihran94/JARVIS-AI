import unittest
from experiments.v72_6_10.resource_policy import ResourcePolicy, IsolationUnavailable
from experiments.v72_6_10.windows_job_policy import (
    compile_job_limits, require_windows_job_host, verify_execution_preconditions,
    JOB_OBJECT_LIMIT_ACTIVE_PROCESS, JOB_OBJECT_LIMIT_PROCESS_MEMORY,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
)

class JobPolicyTests(unittest.TestCase):
    def test_limits_conversion(self):
        result = compile_job_limits(ResourcePolicy(memory_mb=128, max_processes=3))
        self.assertEqual(result.memory_bytes, 128 * 1024 * 1024)
        self.assertEqual(result.active_process_limit, 3)

    def test_required_flags(self):
        flags = compile_job_limits(ResourcePolicy()).flags
        for bit in (JOB_OBJECT_LIMIT_ACTIVE_PROCESS, JOB_OBJECT_LIMIT_PROCESS_MEMORY,
                    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE):
            self.assertTrue(flags & bit)

    def test_bad_policy(self):
        with self.assertRaises(TypeError):
            compile_job_limits(None)

    def test_non_windows_rejected(self):
        with self.assertRaises(IsolationUnavailable):
            require_windows_job_host(platform='posix')

    def test_approval_required(self):
        with self.assertRaises(PermissionError):
            verify_execution_preconditions(policy=ResourcePolicy(), isolation_backend='isolated_vm',
                isolation_verified=True, approval_valid=False, windows_host=True)

    def test_isolation_required(self):
        with self.assertRaises(IsolationUnavailable):
            verify_execution_preconditions(policy=ResourcePolicy(), isolation_backend='isolated_vm',
                isolation_verified=False, approval_valid=True, windows_host=True)

    def test_windows_required(self):
        with self.assertRaises(IsolationUnavailable):
            verify_execution_preconditions(policy=ResourcePolicy(), isolation_backend='isolated_vm',
                isolation_verified=True, approval_valid=True, windows_host=False)

    def test_network_policy_rejected(self):
        with self.assertRaises(IsolationUnavailable):
            verify_execution_preconditions(policy=ResourcePolicy(network_allowed=True),
                isolation_backend='isolated_vm', isolation_verified=True,
                approval_valid=True, windows_host=True)

    def test_valid_preconditions(self):
        result = verify_execution_preconditions(policy=ResourcePolicy(),
            isolation_backend='windows_sandbox', isolation_verified=True,
            approval_valid=True, windows_host=True)
        self.assertEqual(result.active_process_limit, 1)

if __name__ == '__main__':
    unittest.main()
