import unittest
from experiments.v72_6_10.windows_job_lifecycle import JobLifecycle, Phase, UnsafeTransition

class JobLifecycleTests(unittest.TestCase):
    def test_happy_path(self):
        state = JobLifecycle().advance('created_suspended', process_id=42)
        self.assertFalse(state.may_resume)
        state = state.advance('assigned_to_job')
        self.assertFalse(state.may_resume)
        state = state.advance('limits_applied')
        self.assertTrue(state.may_resume)
        state = state.advance('resumed')
        self.assertEqual(state.phase, Phase.RUNNING)
        self.assertEqual(state.advance('close_job').phase, Phase.CLOSED)
    def test_no_resume_before_assignment(self):
        with self.assertRaises(UnsafeTransition):
            JobLifecycle().advance('created_suspended', process_id=1).advance('resumed')
    def test_no_resume_before_limits(self):
        with self.assertRaises(UnsafeTransition):
            JobLifecycle().advance('created_suspended', process_id=1).advance('assigned_to_job').advance('resumed')
    def test_invalid_pid(self):
        for pid in (None, 0, -1, True, '123'):
            with self.subTest(pid=pid), self.assertRaises(UnsafeTransition):
                JobLifecycle().advance('created_suspended', process_id=pid)
    def test_cannot_close_unopened(self):
        with self.assertRaises(UnsafeTransition):
            JobLifecycle().advance('close_job')
    def test_failure_terminal(self):
        state = JobLifecycle().advance('fail')
        with self.assertRaises(UnsafeTransition):
            state.advance('created_suspended', process_id=5)
    def test_closed_terminal(self):
        state = JobLifecycle().advance('created_suspended', process_id=5).advance('close_job')
        with self.assertRaises(UnsafeTransition):
            state.advance('resumed')
    def test_immutable(self):
        start = JobLifecycle()
        next_state = start.advance('created_suspended', process_id=5)
        self.assertEqual(start.phase, Phase.NEW)
        self.assertEqual(next_state.phase, Phase.SUSPENDED)
    def test_duplicate_event_rejected(self):
        state = JobLifecycle().advance('created_suspended', process_id=5)
        with self.assertRaises(UnsafeTransition):
            state.advance('created_suspended', process_id=6)
