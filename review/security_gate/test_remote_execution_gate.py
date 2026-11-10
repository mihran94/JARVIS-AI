import unittest
from remote_execution_gate import ExecutionAuthorization, ExecutionDenied, require_remote_execution_authorization


class RemoteExecutionGateTests(unittest.TestCase):
    def test_defaults_deny(self):
        with self.assertRaises(ExecutionDenied):
            require_remote_execution_authorization(ExecutionAuthorization())

    def test_each_missing_guard_denies(self):
        valid = dict(local_approval=True, paired_device_authenticated=True, capability_granted=True, isolation_verified=True)
        for key in valid:
            with self.subTest(key=key):
                values = valid.copy()
                values[key] = False
                with self.assertRaises(ExecutionDenied):
                    require_remote_execution_authorization(ExecutionAuthorization(**values))

    def test_emergency_stop_denies(self):
        with self.assertRaises(ExecutionDenied):
            require_remote_execution_authorization(ExecutionAuthorization(True, True, True, True, True))

    def test_all_guards_pass(self):
        require_remote_execution_authorization(ExecutionAuthorization(True, True, True, True))
