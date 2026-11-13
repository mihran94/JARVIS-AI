"""Explicit unittest runner for trusted project working copies."""
from pathlib import Path
import sys

HARNESS = '''import sys, unittest
root = sys.argv[1]
sys.path.insert(0, root)
suite = unittest.defaultTestLoader.discover(root + '/tests', pattern='test*.py')
count = suite.countTestCases()
if count == 0:
    print('No tests discovered.', flush=True)
    sys.exit(5)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
'''

def test_command(root):
    root = Path(root).resolve(strict=True)
    if not (root / 'tests').is_dir() or (root / 'tests').is_symlink():
        raise ValueError('A regular tests folder is required at the project root.')
    if getattr(sys, 'frozen', False):
        raise ValueError('This runner requires a source installation with Python available.')
    return [sys.executable, '-I', '-B', '-u', '-c', HARNESS, str(root)]
