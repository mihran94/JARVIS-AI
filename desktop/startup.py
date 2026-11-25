"""Start JARVIS when Windows signs in.

THE OWNER REQUIREMENT
    "Add an opt-in Windows start-at-sign-in setting."

    It is opt-in, it is a Windows-only setting, and it never runs anything
    by itself: the Run key holds the same command the owner already uses to
    start JARVIS, and JARVIS still starts the same way when it is started by
    hand.

HOW IT IS DONE
    The per-user Run key is used, so no administrator rights are needed and
    the setting belongs to the signed-in user. The entry is removed again
    when the setting is switched off, so the owner's machine is left the way
    it was found.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

from core.runtime_profile import APP_NAME

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = APP_NAME


class StartupError(RuntimeError):
    """The start-at-sign-in setting could not be changed."""


def supported() -> bool:
    """True when this machine can start JARVIS at sign-in."""
    return sys.platform == 'win32'


def installation_root() -> Path:
    """The folder JARVIS is installed in."""
    return Path(os.environ.get('JARVIS_INSTALL_ROOT', Path(__file__).resolve().parents[1])).resolve()


def startup_command() -> str:
    """The command the Run key holds.

    It is the same interpreter and the same launcher that START_JARVIS.cmd
    uses, so the application starts exactly the same way either way.
    """
    root = installation_root()
    for candidate in (root / '.venv' / 'Scripts' / 'pythonw.exe',
                      root / '.venv' / 'Scripts' / 'python.exe'):
        if candidate.is_file():
            launcher = root / 'scripts' / 'launch.py'
            if launcher.is_file():
                return f'"{candidate}" "{launcher}"'
    launcher = root / 'scripts' / 'launch.py'
    return f'"{sys.executable}" "{launcher}"'


def start_at_signin_enabled() -> bool:
    """True when JARVIS is set to start at sign-in."""
    if not supported():
        return False
    try:
        import winreg
    except ImportError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(str(value).strip())
    except (FileNotFoundError, OSError):
        return False


def set_start_at_signin(enabled: bool, command: str = '') -> bool:
    """Turn the start-at-sign-in setting on or off.

    Returns the state that is now in place. On a machine that is not
    Windows, nothing is written and the caller is told why.
    """
    if not supported():
        raise StartupError('Starting at sign-in is a Windows setting.')
    try:
        import winreg
    except ImportError as error:  # pragma: no cover - Windows always has winreg
        raise StartupError('Starting at sign-in is a Windows setting.') from error
    value = command or startup_command()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, value)
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
    except OSError as error:
        raise StartupError(
            'Windows would not change the sign-in setting. '
            f'({error.strerror if hasattr(error, "strerror") else error})') from None
    return start_at_signin_enabled()
