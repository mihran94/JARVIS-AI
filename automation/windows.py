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
