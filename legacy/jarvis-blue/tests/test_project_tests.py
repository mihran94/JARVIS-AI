import subprocess, tempfile, unittest
from pathlib import Path
from core.project_tests import test_command

class RunnerTests(unittest.TestCase):
    def test_actual_pass_fail_and_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'tests').mkdir()
            command=test_command(root)
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,5)
            test=root/'tests/test_demo.py'
            test.write_text('import unittest\nclass Demo(unittest.TestCase):\n def test_value(self): self.assertEqual(1,1)\n')
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            test.write_text('import unittest\nclass Demo(unittest.TestCase):\n def test_value(self): self.assertEqual(1,2)\n')
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,1)
    def test_missing_tests_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): test_command(folder)
