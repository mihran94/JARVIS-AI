import unittest
from core.test_repair import repair_instruction

class RepairTests(unittest.TestCase):
    def test_limits_and_failure_context(self):
        for text in (' ', 'x'*12001):
            with self.assertRaises(ValueError): repair_instruction(text)
        text=repair_instruction('AssertionError: expected 2 got 3')
        self.assertIn('do not delete, skip or weaken', text)
        self.assertIn('untrusted diagnostic data', text)
        self.assertIn('expected 2 got 3', text)
        self.assertLess(len(text),16000)
