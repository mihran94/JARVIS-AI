"""Run offline CMD source checks with disposable application and pytest data."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def run_checks(full=False):
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    env.pop('JARVIS_AZURE_LIVE_AUDIO', None)
    env.pop('JARVIS_BROWSER_ACCEPTANCE', None)
    env.pop('GITHUB_ACTIONS', None)
    for label, args in (
        ('Checking the installed runtime', ['scripts/diagnose.py']),
        ('Checking offline checkout startup', ['scripts/launch.py', '--dev-data', '--smoke-test']),
    ):
        print(label, flush=True)
        result = subprocess.call([sys.executable, *args], cwd=ROOT, env=env)
        if result:
            return result

    if importlib.util.find_spec('pytest') is None:
        print('SKIP: pytest is unavailable. Install requirements-dev.txt to run the tests.')
        return int(full)

    with TemporaryDirectory(prefix='jarvis-pytest-') as scratch:
        root = Path(scratch)
        # Pytest otherwise reuses a per-user temp directory from earlier runs.
        env.update(LOCALAPPDATA=str(root / 'app-data'), TEMP=scratch, TMP=scratch,
                   JARVIS_DEVELOPMENT_PROFILE=uuid4().hex[:24])
        targets = [] if full else ['tests/test_omega.py', 'tests/test_mark_lvii_assistant.py']
        return subprocess.call(
            [sys.executable, '-m', 'pytest', '-q', '--basetemp', str(root / 'tests'), *targets],
            cwd=ROOT, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='run the whole source test suite')
    args = parser.parse_args()
    try:
        result = run_checks(full=args.full)
    except OSError:
        print('Could not run verification. Check .venv and Windows temporary-folder access.')
        return 1
    if result:
        print(f'Offline verification failed (exit {result}). Review the test output locally.')
    else:
        print('Offline checks complete. Live device and account acceptance is separate.')
    return result


if __name__ == '__main__':
    raise SystemExit(main())
