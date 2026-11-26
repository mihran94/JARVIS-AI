"""Installation checks and optional same-PC Ollama listing check. No keys or chat history."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def probe_imports():
    # A child process bounds native Qt DLL failures and prevents diagnostic crashes.
    code = ('import PySide6.QtWidgets, httpx, keyring, sqlite3; '
            'db=sqlite3.connect(":memory:"); db.execute("select 1"); db.close()')
    try:
        result = subprocess.run([sys.executable, '-I', '-c', code],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=20, check=False)
    except subprocess.TimeoutExpired:
        return False, 'Dependency import timed out. Repair the virtual environment.'
    except OSError:
        return False, 'Could not start dependency check. Repair Python installation.'
    if result.returncode:
        return False, 'Dependency import failed. Run setup.cmd; check Python and native Qt dependencies.'
    return True, 'Qt, HTTP, keyring and in-memory SQLite imports succeeded.'


def collect():
    checks = []
    def add(name, ok, detail):
        checks.append(dict(name=name, status='pass' if ok else 'fail', detail=detail))
    add('Windows', sys.platform == 'win32',
        'Windows is required for Credential Manager and native automation.')
    add('Python', sys.version_info[:2] == (3, 12),
        'Python 3.12 is the supported setup target; detected ' + platform.python_version())
    add('Architecture', struct.calcsize('P') == 8, '64-bit Python is required.')
    try:
        requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines()
        for line in requirements:
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            name, expected = line.strip().split('==')
            try:
                actual = importlib.metadata.version(name)
                add(name, actual == expected, 'Expected ' + expected + '; installed ' + actual)
            except importlib.metadata.PackageNotFoundError:
                add(name, False, 'Missing package. Run setup.cmd.')
    except (OSError, ValueError):
        add('Requirements', False, 'Cannot read pinned requirements.txt. Extract the complete source archive.')
    ok, detail = probe_imports()
    add('Dependency loading', ok, detail)
    return {'ready': all(c['status'] == 'pass' for c in checks), 'checks': checks,
            'limitations': 'Offline installation check only. Does not verify API access, display rendering, stored credentials or Windows automation.'}


def probe_voice():
    """Check the native speech stack without recording or playback."""
    messages = {
        0: 'System.Speech and SAPI loaded. Microphone and playback require separate tests.',
        21: 'Native Windows speech requires Windows.',
        31: 'Could not initialize pythonnet. Run setup.cmd and check the Windows .NET Framework.',
        32: 'Could not load System.Speech. Check the Windows .NET Framework installation.',
        33: 'System.Speech loaded, but its speech recognition API is unavailable.',
        34: 'Could not import pywin32. Run setup.cmd.',
        35: 'Could not create SAPI.SpVoice. Check Windows speech components.',
        36: 'The Windows speech runtime is incomplete.',
    }
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / 'main.py'), '--check-voice-runtime'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False,
        )
    except subprocess.TimeoutExpired:
        return False, 'The native voice runtime check timed out after 20 seconds.'
    except OSError:
        return False, 'Could not start the native voice runtime check. Check .venv and setup.cmd.'
    code = result.returncode
    return code == 0, messages.get(code, f'Voice runtime check failed (exit {code}).')


def probe_local_model(model):
    # Keep the default diagnostics useful even when the runtime dependencies
    # are missing. Only load the provider for an explicit listing check.
    sys.path.insert(0, str(ROOT))
    try:
        from providers.ollama import probe_model_listing
    except ImportError:
        return False, 'Local Ollama listing check could not load its dependencies.'
    finally:
        sys.path.pop(0)
    return probe_model_listing(model)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--voice', action='store_true', help='also check native speech dependencies')
    parser.add_argument('--local-model', metavar='TAG',
                        help='also check that the running local Ollama server lists TAG')
    args = parser.parse_args(argv)
    report = collect()
    if args.voice:
        ok, detail = probe_voice()
        report['checks'].append(dict(name='Native voice runtime',
                                     status='pass' if ok else 'fail', detail=detail))
        report['ready'] = report['ready'] and ok
    if args.local_model is not None:
        ok, detail = probe_local_model(args.local_model)
        report['checks'].append(dict(name='Local Ollama model listing',
                                     status='pass' if ok else 'fail', detail=detail))
        report['ready'] = report['ready'] and ok
        report['limitations'] += (' The optional loopback listing does not verify model '
                                  'generation, response quality or offline voice.')
    print(json.dumps(report, indent=2))
    return 0 if report['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
