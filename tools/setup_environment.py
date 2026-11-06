"""Explicit setup entry point. Creates/reuses .venv and runs the existing installer."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def setup(root=ROOT):
    if not (3, 11) <= sys.version_info[:2] <= (3, 13):
        print('Setup requires Python 3.11, 3.12 or 3.13. Prefer installed Python 3.12.')
        return 1
    target = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    try:
        if not target.is_file():
            subprocess.run([sys.executable, '-m', 'venv', str(root / '.venv')], cwd=root, check=True)
        result = subprocess.run([str(target), str(root / 'setup.py')], cwd=root)
        if result.returncode:
            print('Setup did not complete. Keep this window open and read the installation error above.')
        else:
            print('Next: double-click START_JARVIS.cmd.')
        return result.returncode
    except (OSError, subprocess.CalledProcessError) as error:
        print('Environment setup failed: ' + type(error).__name__)
        print('Check Python, free disk space and write permission for this folder.')
        return 1

if __name__ == '__main__':
    raise SystemExit(setup())
