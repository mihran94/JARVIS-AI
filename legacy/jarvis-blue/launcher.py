"""Launch Jarvis-Blue with its project environment; never install packages."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
# Probe actual imports in a child process: catches missing native DLLs too.
REQUIRED_IMPORTS = ('PyQt6.QtWidgets', 'sounddevice', 'numpy', 'google.genai',
                    'psutil', 'cryptography')


def environment_python(root=ROOT):
    import os
    return root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def diagnose(python):
    failures = []
    for module in REQUIRED_IMPORTS:
        try:
            result = subprocess.run([str(python), '-c',
                'import importlib, sys; importlib.import_module(sys.argv[1])', module],
                cwd=ROOT, capture_output=True, text=True, errors='replace', timeout=20)
            if result.returncode:
                # Do not dump environment variables or user configuration.
                failures.append(module)
        except subprocess.TimeoutExpired:
            failures.append(module + ' (import timed out)')
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check imports without opening the app')
    args = parser.parse_args(argv)
    python = environment_python()
    if not python.is_file():
        print('Project Python environment is missing. Run SETUP_JARVIS.cmd first.')
        return 1
    try:
        runtime = subprocess.run([str(python), '-c',
            'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)'],
            cwd=ROOT, timeout=10)
        if runtime.returncode:
            print('Use a Python 3.11, 3.12 or 3.13 project environment; 3.12 is preferred.')
            return 1
        failed = diagnose(python)
        if failed:
            print('Startup dependencies unavailable: ' + ', '.join(failed))
            print('Run SETUP_JARVIS.cmd to install or repair dependencies, then retry.')
            return 1
        print('Startup import checks passed.', flush=True)
        if args.check:
            print('GUI, microphone, speakers and model connection still need an app test.')
            return 0
        # Child output stays visible. Normal startup never runs pip or setup.py.
        result = subprocess.run([str(python), str(ROOT / 'main.py')], cwd=ROOT)
        if result.returncode:
            print('Jarvis-Blue stopped with an error. Read the error above; do not share API keys.')
        return result.returncode
    except (OSError, subprocess.TimeoutExpired) as error:
        print('Could not start the project Python environment: ' + type(error).__name__)
        print('Run SETUP_JARVIS.cmd and retry. The project folder may have moved.')
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
