"""Tests for the Qt runtime preparation."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import qt_runtime


def test_the_availability_check_follows_the_loader(monkeypatch):
    monkeypatch.setattr(qt_runtime.ctypes, 'CDLL', lambda name: object())
    assert qt_runtime.egl_is_available() is True

    def refuse(name):
        raise OSError('libEGL.so.1: cannot open shared object file')

    monkeypatch.setattr(qt_runtime.ctypes, 'CDLL', refuse)
    assert qt_runtime.egl_is_available() is False


def test_the_install_runs_the_package_manager(monkeypatch):
    monkeypatch.setattr(qt_runtime.ctypes, 'CDLL', lambda name: object())
    monkeypatch.setattr(qt_runtime.shutil, 'which', lambda name: '/usr/bin/sudo')
    commands = []
    code = qt_runtime.install_egl_runtime(
        run=lambda command: commands.append(command) or 0)
    assert code is True
    assert commands[0][:3] == ['sudo', '-n', 'apt-get']
    assert 'libegl1' in commands[1]


def test_a_failing_command_stops_the_installation(monkeypatch):
    monkeypatch.setattr(qt_runtime.ctypes, 'CDLL', lambda name: object())
    monkeypatch.setattr(qt_runtime.shutil, 'which', lambda name: '/usr/bin/sudo')
    commands = []
    code = qt_runtime.install_egl_runtime(
        run=lambda command: commands.append(command) or 1)
    assert code is False
    assert len(commands) == 1


def test_without_sudo_nothing_is_installed(monkeypatch):
    monkeypatch.setattr(qt_runtime.ctypes, 'CDLL', lambda name: object())
    monkeypatch.setattr(qt_runtime.shutil, 'which', lambda name: None)
    # Windows has no geteuid, so the attribute is added for the test only.
    monkeypatch.setattr(qt_runtime.os, 'geteuid', lambda: 1000, raising=False)
    commands = []
    code = qt_runtime.install_egl_runtime(
        run=lambda command: commands.append(command) or 0)
    assert code is False
    assert commands == []


def test_a_root_account_installs_without_sudo(monkeypatch):
    monkeypatch.setattr(qt_runtime.ctypes, 'CDLL', lambda name: object())
    monkeypatch.setattr(qt_runtime.shutil, 'which', lambda name: None)
    monkeypatch.setattr(qt_runtime.os, 'geteuid', lambda: 0, raising=False)
    commands = []
    code = qt_runtime.install_egl_runtime(
        run=lambda command: commands.append(command) or 0)
    assert code is True
    assert commands[0][0] == 'apt-get'
    assert 'libegl1' in commands[1]


def test_a_windows_machine_needs_nothing(monkeypatch):
    monkeypatch.setattr(qt_runtime, 'egl_is_available', lambda: False)
    called = []
    assert qt_runtime.ensure_egl_runtime(platform='win32',
                                         run=lambda command: called.append(command)) is True
    assert called == []


def test_the_installation_can_be_skipped(monkeypatch):
    monkeypatch.setattr(qt_runtime, 'egl_is_available', lambda: False)
    called = []
    assert qt_runtime.ensure_egl_runtime(platform='linux', skip=True,
                                         run=lambda command: called.append(command)) is False
    assert called == []


def test_the_environment_variable_skips_the_installation(monkeypatch):
    monkeypatch.setattr(qt_runtime, 'egl_is_available', lambda: False)
    monkeypatch.setenv(qt_runtime.SKIP_VARIABLE, '1')
    called = []
    assert qt_runtime.ensure_egl_runtime(platform='linux',
                                         run=lambda command: called.append(command)) is False
    assert called == []


def test_an_available_library_is_left_alone(monkeypatch):
    monkeypatch.setattr(qt_runtime, 'egl_is_available', lambda: True)
    called = []
    assert qt_runtime.ensure_egl_runtime(platform='linux',
                                         run=lambda command: called.append(command)) is True
    assert called == []


def test_the_missing_message_names_the_package():
    message = qt_runtime.missing_message()
    assert 'libEGL.so.1' in message
    assert 'libegl1' in message
