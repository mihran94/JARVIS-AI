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
DEFAULT_TESTS = ('tests/test_omega.py', 'tests/test_mark_lvii_assistant.py')
PHASE1_TESTS = (
    'tests/test_mcore_hud.py',
    'tests/test_settings_views.py',
    'tests/test_command_first_window.py',
    'tests/test_personal_layout.py',
    'tests/test_conversation_plan.py',
)


def run_checks(full=False, *, phase1=False):
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
        if full or phase1:
            print('FAIL: pytest is unavailable; the requested source tests did not run.')
            return 1
        print('SKIP: pytest is unavailable. Install requirements-dev.txt to run the tests.')
        return 0

    with TemporaryDirectory(prefix='jarvis-pytest-') as scratch:
        root = Path(scratch)
        # Pytest otherwise reuses a per-user temp directory from earlier runs.
        env.update(LOCALAPPDATA=str(root / 'app-data'), TEMP=scratch, TMP=scratch,
                   JARVIS_DEVELOPMENT_PROFILE=uuid4().hex[:24])
        targets = () if full else PHASE1_TESTS if phase1 else DEFAULT_TESTS
        return subprocess.call(
            [sys.executable, '-m', 'pytest', '-q', '--basetemp', str(root / 'tests'), *targets],
            cwd=ROOT, env=env)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    suites = parser.add_mutually_exclusive_group()
    suites.add_argument('--full', action='store_true', help='run the whole source test suite')
    suites.add_argument('--phase1', action='store_true',
                        help='run M-CORE HUD, Settings, layout and approval source tests')
    args = parser.parse_args(argv)
    try:
        result = run_checks(full=args.full, phase1=args.phase1)
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
