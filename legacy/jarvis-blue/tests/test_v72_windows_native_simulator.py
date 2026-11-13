import unittest
from dataclasses import replace
from experiments.v72_6_10.windows_native_simulator import simulate_native_sequence, RecordingBackend
from experiments.v72_6_10.windows_native_adapter import Operation, NativeExecutionUnavailable
from experiments.v72_6_10.windows_execution_preflight import ExecutionPlan
from experiments.v72_6_10.resource_policy import ResourcePolicy
from experiments.v72_6_10.windows_job_policy import compile_job_limits

class NativeSimulatorTests(unittest.TestCase):
    def plan(self):
        return ExecutionPlan(compile_job_limits(ResourcePolicy()), 'windows-vm-job-object')
    def test_success_sequence(self):
        result = simulate_native_sequence(self.plan())
        self.assertTrue(result.completed)
        self.assertTrue(result.cleanup_attempted)
        self.assertEqual(len(result.operations), 5)
    def test_failure_before_job_assignment_cleans_up(self):
        result = simulate_native_sequence(self.plan(), Operation.CREATE_SUSPENDED)
        self.assertFalse(result.completed)
        self.assertEqual(result.operations[-1], Operation.CLOSE_JOB.value)
    def test_failure_on_assignment_cleans_up(self):
        result = simulate_native_sequence(self.plan(), Operation.ASSIGN_JOB)
        self.assertFalse(result.completed)
        self.assertTrue(result.cleanup_attempted)
    def test_failure_on_limits_never_resumes(self):
        result = simulate_native_sequence(self.plan(), Operation.SET_LIMITS)
        self.assertNotIn(Operation.RESUME.value, result.operations)
    def test_failure_on_resume_cleans_up(self):
        result = simulate_native_sequence(self.plan(), Operation.RESUME)
        self.assertFalse(result.completed)
        self.assertTrue(result.cleanup_attempted)
    def test_cleanup_failure(self):
        result = simulate_native_sequence(self.plan(), Operation.CLOSE_JOB)
        self.assertFalse(result.completed)
        self.assertEqual(result.error, 'simulated cleanup failure')
    def test_reject_modified_plan(self):
        with self.assertRaises(NativeExecutionUnavailable):
            simulate_native_sequence(replace(self.plan(), executable=True))
    def test_reject_wrong_backend(self):
        with self.assertRaises(NativeExecutionUnavailable):
            simulate_native_sequence(replace(self.plan(), backend='host'))
    def test_reject_invalid_failure_injection(self):
        with self.assertRaises(TypeError): simulate_native_sequence(self.plan(), 'RESUME')
    def test_recording_backend_no_win32(self):
        backend = RecordingBackend()
        backend.record(Operation.ASSIGN_JOB)
        self.assertEqual(backend.operations, [Operation.ASSIGN_JOB.value])
    def test_record_invalid_operation(self):
        with self.assertRaises(TypeError): RecordingBackend().record('execute')

if __name__ == '__main__': unittest.main()
