import unittest
from dataclasses import replace
from experiments.v72_6_10.windows_native_adapter import (
    describe_native_sequence, execute_native, NativeExecutionUnavailable, Operation
)
from experiments.v72_6_10.windows_execution_preflight import ExecutionPlan
from experiments.v72_6_10.windows_job_policy import JobLimits

class NativeAdapterTests(unittest.TestCase):
    def make_plan(self):
        from experiments.v72_6_10.resource_policy import ResourcePolicy
        from experiments.v72_6_10.windows_job_policy import compile_job_limits
        return ExecutionPlan(compile_job_limits(ResourcePolicy()), 'windows-vm-job-object')

    def test_sequence(self):
        steps = describe_native_sequence(self.make_plan())
        self.assertEqual(len(steps), 5)
        self.assertEqual(steps[0].operation, Operation.CREATE_SUSPENDED)
        self.assertEqual(steps[-1].operation, Operation.CLOSE_JOB)
        for a,b in zip(steps,steps[1:]):
            self.assertEqual(a.next_phase,b.required_phase)
    def test_wrong_type(self):
        with self.assertRaises(TypeError): describe_native_sequence(None)
    def test_modified_executable(self):
        with self.assertRaises(NativeExecutionUnavailable):
            describe_native_sequence(replace(self.make_plan(), executable=True))
    def test_no_approval_required(self):
        with self.assertRaises(NativeExecutionUnavailable):
            describe_native_sequence(replace(self.make_plan(), requires_single_use_approval=False))
    def test_wrong_backend(self):
        with self.assertRaises(NativeExecutionUnavailable):
            describe_native_sequence(replace(self.make_plan(), backend='host'))
    def test_native_launch_always_denied(self):
        with self.assertRaises(NativeExecutionUnavailable): execute_native('anything')
    def test_native_launch_noargs_denied(self):
        with self.assertRaises(NativeExecutionUnavailable): execute_native()
if __name__ == '__main__': unittest.main()
