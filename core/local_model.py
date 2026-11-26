"""The on-device model that JARVIS starts on this computer.

WHAT THIS IS
    JARVIS is local first, so the model that answers most of the work has
    to actually be running. Ollama serves the local models on the loopback
    interface of this computer: no key, no account, no network egress.

    This module finds Ollama, checks whether it is already serving, and
    starts it when it is not. It never binds an address other than the
    loopback interface, and it never sends a request anywhere else.

THE RULES
    * The endpoint is the loopback interface and nothing else. A local
      model must not be turned into an open relay by pointing it at
      another port on another machine.
    * Only Ollama's own `serve` command is run, with no arguments from a
      model, a message or the owner.
    * A model that is not installed is reported as missing. It is never
      downloaded: that is the owner's decision, not the assistant's.

WHAT THIS IS NOT
    * It is not a provider client. The request shape belongs to
      `providers.ollama`; this module only decides whether the local
      model is there.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import httpx

#: The address the local model is reached on. The loopback interface only.
LOCAL_HOST = '127.0.0.1'

#: The port Ollama serves on by default.
DEFAULT_PORT = 11434

#: The base address of the local model server.
DEFAULT_BASE = f'http://{LOCAL_HOST}:{DEFAULT_PORT}'

#: The address the chat interface uses for the local provider.
DEFAULT_ENDPOINT = f'{DEFAULT_BASE}/v1/chat/completions'

#: The model JARVIS asks for when the owner has not chosen one.
DEFAULT_MODEL = 'qwen3:8b'

#: The name of the executable, per platform.
EXECUTABLE = 'ollama.exe' if sys.platform == 'win32' else 'ollama'

#: How long a check of the local server may take, in seconds.
CHECK_TIMEOUT = 2.0

#: How long a check of the local server may take when the interface is
#: waiting for it, in seconds. The local server answers in a moment or
#: it is not there at all, so a short wait is enough.
STATUS_TIMEOUT = 0.5

#: How long the supervisor waits for a server it started, in seconds.
START_TIMEOUT = 12.0


class LocalModelUnavailable(RuntimeError):
    """The on-device model could not be reached or started."""


@dataclass
class LocalModelStatus:
    """What the interface shows about the on-device model."""

    installed: bool = False
    running: bool = False
    models: list = field(default_factory=list)
    model: str = ''
    started: bool = False
    detail: str = ''

    @property
    def ready(self) -> bool:
        """True when the model JARVIS wants can answer right now."""
        return bool(self.running and self.model and self.model in self.models)

    def as_dict(self) -> dict:
        return {'installed': self.installed, 'running': self.running,
                'models': list(self.models), 'model': self.model,
                'started': self.started, 'detail': self.detail, 'ready': self.ready}


def is_loopback(url: str) -> bool:
    """True when the URL points at this machine."""
    from urllib.parse import urlparse
    try:
        host = (urlparse(url).hostname or '').lower()
    except ValueError:
        return False
    return host in (LOCAL_HOST, '::1', 'localhost')


def candidate_paths() -> list:
    """Where Ollama is looked for, in order."""
    paths = []
    local_app = os.environ.get('LOCALAPPDATA')
    program_files = os.environ.get('ProgramFiles')
    if local_app:
        paths.append(Path(local_app) / 'Programs' / 'Ollama' / EXECUTABLE)
    if program_files:
        paths.append(Path(program_files) / 'Ollama' / EXECUTABLE)
    found = shutil.which(EXECUTABLE)
    if found:
        paths.append(Path(found))
    found_any = shutil.which('ollama')
    if found_any:
        paths.append(Path(found_any))
    unique = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def find_executable() -> str:
    """The Ollama executable, or an empty string when there is none."""
    for path in candidate_paths():
        try:
            if path.is_file():
                return str(path)
        except OSError:
            continue
    return ''


class LocalModelSupervisor:
    """Keeps the on-device model available on this computer."""

    def __init__(self, *, base: str = DEFAULT_BASE, model: str = DEFAULT_MODEL,
                 executable: str = '', transport=None, timeout: float = CHECK_TIMEOUT):
        if not is_loopback(base):
            raise ValueError('The local model may only be reached on the loopback interface.')
        self.base = base.rstrip('/')
        self.model = model or DEFAULT_MODEL
        self._executable = executable
        self._transport = transport
        self.timeout = timeout
        self._process = None

    # ------------------------------------------------------------------

    @property
    def executable(self) -> str:
        """The Ollama executable, or an empty string when there is none."""
        return self._executable or find_executable()

    @property
    def endpoint(self) -> str:
        """The address the chat interface uses."""
        return f'{self.base}/v1/chat/completions'

    def _get(self, path: str):
        with httpx.Client(timeout=self.timeout, follow_redirects=False,
                          transport=self._transport) as client:
            response = client.get(f'{self.base}{path}')
        return response

    def installed_models(self) -> list:
        """The models the local server has, newest names first.

        An empty list means the server is not there or has no models.
        """
        try:
            response = self._get('/api/tags')
        except Exception:
            return []
        if response.status_code != 200:
            return []
        try:
            payload = response.json()
        except Exception:
            return []
        models = []
        for entry in payload.get('models', []) or []:
            name = entry.get('name') or entry.get('model')
            if isinstance(name, str) and name:
                models.append(name)
        return models

    def is_running(self) -> bool:
        """Whether the local server is answering."""
        try:
            response = self._get('/api/tags')
        except Exception:
            return False
        return response.status_code == 200

    def status(self) -> LocalModelStatus:
        """What the interface shows about the on-device model."""
        executable = self.executable
        installed = bool(executable)
        if installed:
            try:
                installed = Path(executable).is_file()
            except OSError:
                installed = False
        running = self.is_running()
        models = self.installed_models() if running else []
        if not running:
            if not installed:
                detail = ('The on-device model is not installed. Install Ollama on this '
                          'computer, then JARVIS can start it and answer without a key.')
            else:
                detail = 'The on-device model is installed but not running yet.'
        elif self.model not in models:
            detail = ('The on-device model is running, but the model '
                      f'{self.model} is not installed. Installed: '
                      + (', '.join(models) if models else 'none') + '.')
        else:
            detail = f'The on-device model {self.model} is ready on this computer.'
        return LocalModelStatus(installed=installed, running=running, models=models,
                                model=self.model, started=False, detail=detail)

    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start the local server, and wait for it to answer.

        The server is bound to the loopback interface only. It is started
        without a console window on Windows, and its output is discarded
        so it cannot fill a pipe.
        """
        executable = self.executable
        if not executable:
            raise LocalModelUnavailable(
                'The on-device model is not installed on this computer.')
        if self.is_running():
            return False
        environment = dict(os.environ)
        environment['OLLAMA_HOST'] = f'{LOCAL_HOST}:{DEFAULT_PORT}'
        creation = 0
        if sys.platform == 'win32':
            creation = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        try:
            self._process = subprocess.Popen(
                [executable, 'serve'], env=environment, shell=False,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=creation)
        except OSError as error:
            raise LocalModelUnavailable(
                'The on-device model could not be started: ' + str(error)) from None
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if self.is_running():
                return True
            if self._process.poll() is not None:
                raise LocalModelUnavailable(
                    'The on-device model stopped before it could answer.')
            time.sleep(0.25)
        raise LocalModelUnavailable(
            'The on-device model did not answer within '
            f'{int(START_TIMEOUT)} seconds.')

    def ensure_running(self) -> LocalModelStatus:
        """Make sure the on-device model is available, and report on it."""
        try:
            self.start()
        except LocalModelUnavailable:
            return self.status()
        status = self.status()
        status.started = True
        return status

    def stop(self) -> None:
        """Stop the server this supervisor started."""
        process, self._process = self._process, None
        if process is None:
            return
        try:
            process.terminate()
        except OSError:
            pass

    def choose_model(self, available=None) -> str:
        """The model JARVIS should use, from the models that are there.

        The owner's choice wins. Otherwise the default model is used when
        it is installed, and otherwise the first model that is there.
        """
        models = list(available) if available is not None else self.installed_models()
        if not models:
            return self.model
        if self.model in models:
            return self.model
        for candidate in models:
            if candidate.split(':')[0] == self.model.split(':')[0]:
                return candidate
        return models[0]


__all__ = ['CHECK_TIMEOUT', 'DEFAULT_BASE', 'DEFAULT_ENDPOINT', 'DEFAULT_MODEL',
           'DEFAULT_PORT', 'EXECUTABLE', 'LOCAL_HOST', 'LocalModelStatus',
           'LocalModelSupervisor', 'LocalModelUnavailable', 'START_TIMEOUT',
           'STATUS_TIMEOUT', 'candidate_paths', 'find_executable', 'is_loopback']
