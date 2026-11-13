import unittest
from core.coding_prompts import PROMPTS, draft_prompt

class PromptTests(unittest.TestCase):
    def test_templates_have_explicit_scope(self):
        self.assertGreaterEqual(len(PROMPTS), 5)
        prompt = draft_prompt('demo.py', 'Fix validation', 'print(1)')
        self.assertIn('cannot edit other files', prompt)
        self.assertIn('Do not claim', prompt)
        self.assertIn('print(1)', prompt)

    def test_input_limits(self):
        for instruction, content in [('', ''), ('x'*16001, ''), ('fix', 'a'*131073)]:
            with self.assertRaises(ValueError): draft_prompt('demo.py', instruction, content)
