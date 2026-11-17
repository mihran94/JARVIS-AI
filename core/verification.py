"""Run a project's own tests in a prepared folder and keep the result.

Every prepared change — a downloaded source candidate or a worktree that
JARVIS improved — is verified the same way: the test command runs inside the
prepared folder, and the outcome is kept as a small record the owner can
read. A failed run is not a detail to be hidden; it is the reason the Apply
button stays disabled.
"""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys
import time


class TestRunError(RuntimeError):
    """The tests could not be run at all."""


def python_for(folder: Path) -> str:
    """The interpreter to run the tests with.

    The project's own virtual environment is used when it is there, because
    that is the environment the owner runs the application in.
    """
    for candidate in (Path(folder) / '.venv' / 'Scripts' / 'python.exe',
                      Path(folder) / '.venv' / 'bin' / 'python'):
        if candidate.is_file():
            return str(candidate)
    interpreter = Path(sys.executable)
    if interpreter.name.lower() == 'pythonw.exe':
        console_python = interpreter.with_name('python.exe')
        if console_python.is_file():
            return str(console_python)
    return sys.executable


def split_command(command: str) -> list[str]:
    """Split a configured test command into its parts."""
    text = (command or '').strip()
    if not text:
        raise TestRunError('No test command is configured.')
    if os.name == 'nt':
        parts = shlex.split(text, posix=False)
        return [part.strip('"') for part in parts if part.strip('"')]
    return shlex.split(text)


def run_tests(folder, command: str, *, timeout: int = 1800, cancel=None) -> dict:
    """Run the test command in `folder` and return the outcome.

    The result is a dictionary with the status, a one line summary and the
    output. `cancel` is called while the command runs, so an emergency stop
    or a closing window ends the run instead of waiting for it.
    """
    parts = split_command(command)
    folder = Path(folder)
    if not folder.is_dir():
        raise TestRunError('The prepared folder is not there any more.')
    if not parts:
        raise TestRunError('No test command is configured.')
    # A bare "pytest" is run with the project's interpreter, so the tests use
    # the environment the owner set up.
    if Path(parts[0]).name.lower() in {'pytest', 'py.test'}:
        parts = [python_for(folder)] + ['-m', 'pytest'] + parts[1:]
    try:
        process = subprocess.Popen(
            parts, cwd=str(folder), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
    except OSError as error:
        raise TestRunError(f'The test command could not be started: {error}') from None
    deadline = time.monotonic() + timeout
    try:
        while True:
            if cancel is not None:
                cancel()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TestRunError(f'The tests did not finish within {timeout // 60} minutes.')
            try:
                output, _ = process.communicate(timeout=min(remaining, 0.25))
                break
            except subprocess.TimeoutExpired:
                continue
        if cancel is not None:
            cancel()
    finally:
        if process.poll() is None:
            process.kill()
            if process.stdout is not None:
                process.stdout.close()
            process.wait()
    return {
        'status': 'passed' if process.returncode == 0 else 'failed',
        'code': process.returncode,
        'summary': summarize(output),
        'output': (output or '')[-20000:],
    }


def summarize(output: str, limit: int = 240) -> str:
    """One line that says what the test run did."""
    lines = [line.strip() for line in (output or '').splitlines() if line.strip()]
    if not lines:
        return 'The test command produced no output.'
    for line in reversed(lines):
        if 'passed' in line or 'failed' in line or 'error' in line.lower():
            return line[:limit]
    return lines[-1][:limit]
