"""Stable bootstrap; keeps the original virtual environment and source for recovery."""
from contextlib import nullcontext
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.updates import read_state, release_path
# The child returns this status when it has fully closed for restart.
RESTART_EXIT_CODE = 75


def main(args=()):
    development = '--dev-data' in args
    reviewed_dev_updates = '--test-reviewed-updates' in args
    args = [arg for arg in args if arg not in ('--dev-data', '--test-reviewed-updates')]
    if reviewed_dev_updates and (not development or '--smoke-test' in args):
        print('--test-reviewed-updates requires an interactive --dev-data launch.')
        return 2
    try:
        env = dict(os.environ, JARVIS_INSTALL_ROOT=str(ROOT), JARVIS_RESTART_MANAGED='1')
        env.pop('JARVIS_BUILD_COMMIT', None)
        env.pop('JARVIS_DEVELOPMENT_PROFILE', None)
        env.pop('JARVIS_RESTART_REVIEWED_DEV', None)
        if reviewed_dev_updates:
            env['JARVIS_RESTART_REVIEWED_DEV'] = '1'
        smoke = '--smoke-test' in args
        temporary = TemporaryDirectory(prefix='jarvis-verify-') if smoke else nullcontext()
        with temporary as scratch:
            if scratch is not None:
                env['LOCALAPPDATA'] = scratch
            if development or smoke:
                profile_path = scratch or os.path.normcase(str(ROOT.resolve()))
                env['JARVIS_DEVELOPMENT_PROFILE'] = hashlib.sha256(
                    os.fsencode(profile_path)).hexdigest()[:24]
            selected = 'base' if development else read_state(ROOT)['active']
            previous_active = read_state(ROOT)['active'] if reviewed_dev_updates else 'base'
            while True:
                target = release_path(ROOT, selected)
                if not (target / 'main.py').is_file():
                    raise ValueError('Selected release is missing main.py.')
                env['JARVIS_SOURCE_RELEASE'] = selected
                result = subprocess.call(
                    [sys.executable, str(target / 'main.py'), *args], cwd=target, env=env)
                if result != RESTART_EXIT_CODE or smoke:
                    return result
                if not development:
                    selected = read_state(ROOT)['active']
                elif reviewed_dev_updates:
                    active = read_state(ROOT)['active']
                    if active != previous_active:
                        selected = previous_active = active
    except (OSError, ValueError):
        print('Cannot start selected release. Run ROLLBACK_JARVIS.cmd or original main.py.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
