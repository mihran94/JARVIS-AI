"""Stable bootstrap; keeps the original virtual environment and source for recovery."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.updates import read_state, release_path


def main(args=()):
    try:
        selected = read_state(ROOT)['active']
        target = release_path(ROOT, selected)
        if not (target / 'main.py').is_file():
            raise ValueError('Selected release is missing main.py.')
        env = dict(os.environ, JARVIS_INSTALL_ROOT=str(ROOT))
        env.pop('JARVIS_BUILD_COMMIT', None)
        env['JARVIS_SOURCE_RELEASE'] = selected
        return subprocess.call([sys.executable, str(target / 'main.py'), *args], cwd=target, env=env)
    except (OSError, ValueError):
        print('Cannot start selected release. Run ROLLBACK_JARVIS.cmd or original main.py.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
