import unittest
from experiments.v72_6_10.native_trace_verifier import assess_trace
from experiments.v72_6_10.windows_native_simulator import SimulationResult, simulate_native_sequence
from experiments.v72_6_10.windows_native_adapter import Operation
from experiments.v72_6_10.windows_execution_preflight import ExecutionPlan
from experiments.v72_6_10.windows_job_policy import compile_job_limits
from experiments.v72_6_10.resource_policy import ResourcePolicy

class TraceVerifierTests(unittest.TestCase):
    def plan(self):
        return ExecutionPlan(compile_job_limits(ResourcePolicy()), 'windows-vm-job-object')
    def test_success(self):
        self.assertTrue(assess_trace(simulate_native_sequence(self.plan())).valid)
    def test_failure_at_each_step(self):
        for op in Operation:
            with self.subTest(op=op):
                result = simulate_native_sequence(self.plan(), op)
                self.assertTrue(assess_trace(result).valid)
    def test_wrong_type(self):
        with self.assertRaises(TypeError): assess_trace(None)
    def test_empty_trace(self):
        self.assertFalse(assess_trace(SimulationResult((),False,False,'failure')).valid)
    def test_missing_cleanup(self):
        self.assertFalse(assess_trace(SimulationResult((Operation.CREATE_SUSPENDED.value,),False,False,'failure')).valid)
    def test_out_of_order(self):
        self.assertFalse(assess_trace(SimulationResult((Operation.RESUME.value,Operation.CLOSE_JOB.value),True,False,'failure')).valid)
    def test_duplicate_operation(self):
        a=Operation.CREATE_SUSPENDED.value
        self.assertFalse(assess_trace(SimulationResult((a,a,Operation.CLOSE_JOB.value),True,False,'failure')).valid)
    def test_false_success(self):
        self.assertFalse(assess_trace(SimulationResult((Operation.CREATE_SUSPENDED.value,Operation.CLOSE_JOB.value),True,True,None)).valid)
    def test_failure_without_error(self):
        self.assertFalse(assess_trace(SimulationResult((Operation.CREATE_SUSPENDED.value,Operation.CLOSE_JOB.value),True,False,None)).valid)
    def test_malformed_trace(self):
        self.assertFalse(assess_trace(SimulationResult((42,),True,False,'failure')).valid)
    def test_duplicate_cleanup(self):
        self.assertFalse(assess_trace(SimulationResult((Operation.CLOSE_JOB.value,Operation.CLOSE_JOB.value),True,False,'failure')).valid)

if __name__ == '__main__': unittest.main()
