"""Fixed allowlist: never run a path, command or arguments from the model."""
import ctypes
from pathlib import Path
import subprocess
import sys

APPS = {'Notepad': 'notepad.exe', 'Calculator': 'calc.exe'}


def launch_app(name):
    if name not in APPS:
        raise ValueError('Application is not allowlisted.')
    if sys.platform != 'win32':
        raise RuntimeError('Application launching is available on Windows only.')
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not length or length >= len(buffer):
        raise RuntimeError('Cannot resolve the Windows system directory.')
    executable = Path(buffer.value) / APPS[name]
    if not executable.is_file():
        raise RuntimeError('This Windows application is not installed.')
    process = subprocess.Popen([str(executable)], shell=False, close_fds=True)
    return f'Launch request accepted; process ID {process.pid}. Verify the app window on your desktop.'


EDITOR_EXECUTABLES = {
    'CapCut': 'CapCut.exe',
    'DaVinci Resolve': 'Resolve.exe',
    'After Effects': 'AfterFX.exe',
}


def editor_executable(name, value):
    expected = EDITOR_EXECUTABLES[name]
    if not value:
        raise ValueError(f'Choose the installed {expected} in Settings → Plugins.')
    path = Path(value)
    if not path.is_absolute() or path.name.casefold() != expected.casefold() or not path.is_file():
        raise ValueError(f'Choose an existing {expected} in Settings → Plugins.')
    return path.resolve(strict=True)


def launch_editor(name, value):
    if sys.platform != 'win32':
        raise RuntimeError('Editor launching is available on Windows only.')
    executable = editor_executable(name, value)
    process = subprocess.Popen([str(executable)], shell=False, close_fds=True)
    return f'{name} launch requested (process {process.pid}).'
