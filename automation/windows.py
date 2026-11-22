"""Fixed allowlist: never run a path, command or arguments from the model."""
import ctypes
from pathlib import Path
import subprocess
import sys

APPS = {'Notepad': 'notepad.exe', 'Calculator': 'calc.exe'}


class LaunchRequest(str):
    """A dispatched native launch and its OS-assigned process identity."""

    def __new__(cls, name, pid):
        result = super().__new__(cls, f'Launch requested for {name} (process {pid}).')
        result.pid = pid
        return result


def launch_is_foreground(request):
    """Confirm a visible foreground window belongs to the dispatched process."""
    from automation.win_controls import foreground_process

    return foreground_process() == request.pid


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
    return LaunchRequest(name, process.pid)


def open_path(path):
    """Open a file with its own program, or a folder, on this computer.

    The path is one the owner chose. Nothing is run from it: a file is
    handed to the program Windows has associated with it, and a folder is
    opened in Explorer. A path that is not there, or that is a link, is
    refused rather than followed.
    """
    if sys.platform != 'win32':
        raise RuntimeError('Opening a file is available on Windows only.')
    target = Path(path).expanduser()
    if target.is_symlink():
        raise ValueError('Choose the real file or folder, not a link.')
    if not target.exists():
        raise ValueError('That file or folder is not there.')
    if not (target.is_file() or target.is_dir()):
        raise ValueError('That is not a file or a folder.')
    import os
    os.startfile(str(target))
    kind = 'folder' if target.is_dir() else 'file'
    return f'Open request accepted for the {kind} {target.name}. Check your desktop.'


EDITOR_EXECUTABLES = {
    'CapCut': 'CapCut.exe',
    'DaVinci Resolve': 'Resolve.exe',
    'After Effects': 'AfterFX.exe',
    'Photoshop': 'Photoshop.exe',
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
    return LaunchRequest(name, process.pid)
