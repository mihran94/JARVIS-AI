from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import launcher
from tools import setup_environment


class LauncherTests(unittest.TestCase):
    def test_missing_environment_does_not_install(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(launcher, 'environment_python', return_value=Path(directory)/'missing'), patch.object(launcher.subprocess, 'run') as run:
                self.assertEqual(launcher.main([]), 1)
                run.assert_not_called()

    def test_check_does_not_launch_main(self):
        with patch.object(launcher.Path, 'is_file', return_value=True), patch.object(launcher, 'diagnose', return_value=[]), patch.object(launcher.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(launcher.main(['--check']), 0)
            self.assertEqual(run.call_count, 1)
            self.assertNotIn('main.py', str(run.call_args))

    def test_import_failure_does_not_launch_main(self):
        with patch.object(launcher.Path, 'is_file', return_value=True), patch.object(launcher, 'diagnose', return_value=['sounddevice']), patch.object(launcher.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(launcher.main([]), 1)
            self.assertEqual(run.call_count, 1)

    def test_native_import_failure_and_timeout_are_reported(self):
        with patch.object(launcher, 'REQUIRED_IMPORTS', ('missing.dll', 'slow.module')), patch.object(launcher.subprocess, 'run', side_effect=[SimpleNamespace(returncode=1), subprocess.TimeoutExpired('probe', 20)]):
            self.assertEqual(launcher.diagnose(Path('python')), ['missing.dll', 'slow.module (import timed out)'])

    def test_launch_preserves_child_failure(self):
        with patch.object(launcher.Path, 'is_file', return_value=True), patch.object(launcher, 'diagnose', return_value=[]), patch.object(launcher.subprocess, 'run', side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=7)]) as run:
            self.assertEqual(launcher.main([]), 7)
            self.assertEqual(run.call_args.kwargs['cwd'], launcher.ROOT)

    def test_setup_uses_exact_paths_and_preserves_failure(self):
        with tempfile.TemporaryDirectory(prefix='jarvis space ') as directory:
            root = Path(directory)
            with patch.object(setup_environment.Path, 'is_file', return_value=False), patch.object(setup_environment.subprocess, 'run', side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=5)]) as run:
                self.assertEqual(setup_environment.setup(root), 5)
                self.assertEqual(run.call_args_list[0].args[0][-1], str(root / '.venv'))
                self.assertEqual(run.call_args.kwargs['cwd'], root)
                self.assertEqual(run.call_args.args[0][-1], str(root / 'setup.py'))

if __name__ == '__main__':
    unittest.main()
