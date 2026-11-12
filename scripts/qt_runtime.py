"""Make the Qt runtime usable on a Linux machine that has no EGL libraries.

The Qt 6 libraries that PySide6 uses are linked against ``libEGL.so.1``.
Many minimal Linux images, including the GitHub Actions runner, do not ship
that library, so importing PySide6 fails with::

    ImportError: libEGL.so.1: cannot open shared object file

This module installs the missing runtime library with the system package
manager. It is used by the repository ``conftest.py`` before the test modules
are imported, so the whole test suite runs on the runner.

Nothing here changes the application. The library is only a runtime
dependency of the Qt binaries that PySide6 already installs.
"""
import ctypes
import os
import shutil
import subprocess
import sys

EGL_LIBRARY = 'libEGL.so.1'
EGL_PACKAGE = 'libegl1'
COMMAND_TIMEOUT_SECONDS = 300
SKIP_VARIABLE = 'JARVIS_SKIP_SYSTEM_PACKAGES'


def egl_is_available():
    """True when the EGL runtime library can be loaded."""
    try:
        ctypes.CDLL(EGL_LIBRARY)
        return True
    except OSError:
        return False


def apt_prefix():
    """How the package manager is reached.

    A normal machine needs `sudo`, because the runner account is not root. A
    container that already runs as root has no `sudo` at all, so the command
    is run directly there.
    """
    if shutil.which('sudo') is not None:
        return ['sudo', '-n']
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        return []
    return None


def apt_commands():
    """The commands that install the EGL runtime library."""
    prefix = apt_prefix()
    if prefix is None:
        return []
    return [
        prefix + ['apt-get', 'update', '-qq'],
        prefix + ['apt-get', 'install', '-y', '-qq', EGL_PACKAGE],
    ]


def _run_command(command):
    """Run a command and return its exit code, or None when it cannot run."""
    try:
        completed = subprocess.run(command, timeout=COMMAND_TIMEOUT_SECONDS,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except (subprocess.SubprocessError, OSError):
        return None
    if completed.returncode != 0:
        output = completed.stdout.decode('utf-8', 'replace').strip()
        if output:
            print(output[-2000:])
    return completed.returncode


def install_egl_runtime(run=None, which=None):
    """Install the EGL runtime library with the system package manager.

    ``run`` and ``which`` are injection points for the tests. Returns True
    when the library is loadable afterwards.
    """
    if run is None:
        run = _run_command
    if which is None:
        which = shutil.which
    commands = apt_commands()
    if not commands:
        print('Neither sudo nor a root account is available, so the EGL runtime '
              'cannot be installed.')
        return False
    for command in commands:
        code = run(command)
        if code != 0:
            print('%s failed with exit code %s' % (' '.join(command), code))
            return False
    return egl_is_available()


def ensure_egl_runtime(platform=None, skip=None, run=None, which=None):
    """Make sure the EGL runtime library is usable.

    Returns True when the library is available, also on platforms that do not
    need it. Set the environment variable ``JARVIS_SKIP_SYSTEM_PACKAGES`` to a
    true value to never install anything.
    """
    if platform is None:
        platform = sys.platform
    if not platform.startswith('linux'):
        return True
    if egl_is_available():
        return True
    if skip is None:
        skip = os.environ.get(SKIP_VARIABLE, '').strip().lower() not in ('', '0', 'false')
    if skip:
        print('%s is set, so the EGL runtime is not installed.' % SKIP_VARIABLE)
        return False
    print('%s is missing. Installing the Qt runtime library.' % EGL_LIBRARY)
    installed = install_egl_runtime(run=run, which=which)
    if installed:
        print('Installed %s.' % EGL_LIBRARY)
    return installed


def missing_message():
    """The message shown when the EGL runtime cannot be provided."""
    return (
        'The Qt runtime library %s is not available on this machine and it could '
        'not be installed. Install the package %s (for example '
        '"sudo apt-get install %s") or set %s=1 to skip the automatic '
        'installation.' % (EGL_LIBRARY, EGL_PACKAGE, EGL_PACKAGE, SKIP_VARIABLE)
    )
