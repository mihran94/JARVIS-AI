"""The editors JARVIS can open a project in, and what each one can do.

WHAT THIS IS
    The owner saves a project folder and says which editor they work in. JARVIS
    then opens that project in THAT editor, in the real folder, and tells the
    owner honestly when the editor is not installed.

WHY CAPABILITIES ARE PER EDITOR
    Not every editor can do every thing. VS Code opens a folder and a file.
    Visual Studio builds and debugs. PyCharm runs its own test runner. If
    JARVIS says "Run tests" for an editor that cannot run tests, the owner
    gets a promise the tool cannot keep.

    So each editor declares what it can do, and the interface shows those
    capabilities one by one. An editor JARVIS finds has no capabilities at all
    until it is configured, and a configured launcher states its own.

    A CONFIGURED LAUNCHER IS THE OWNER'S OWN EDITOR
    The owner can add any launcher: a name, the command that starts it, and
    the capabilities they want it to have. The command is stored, never
    executed until the owner approves that exact action, and it is shown in
    full before it runs.

WHAT THIS MODULE WILL NOT DO
    * It never launches anything. It only reports what is installed and where.
    * It never guesses that an editor is present. "Setup needed" is the honest
      answer when the executable is not there.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys

from developer_studio.intents import summary_labels


#: What an editor can be asked to do. The interface shows these individually.
CAP_OPEN_PROJECT = 'open_project'
CAP_OPEN_FILE = 'open_file'
CAP_BUILD = 'build'
CAP_RUN_TESTS = 'run_tests'

CAPABILITY_LABELS = {
    CAP_OPEN_PROJECT: 'Open the project',
    CAP_OPEN_FILE: 'Open a file',
    CAP_BUILD: 'Build',
    CAP_RUN_TESTS: 'Run its tests',
}


@dataclass(frozen=True)
class EditorSpec:
    """One editor JARVIS knows how to look for."""

    name: str
    #: The command that starts it, looked up on PATH.
    command: str
    #: What this editor can be asked to do.
    capabilities: tuple[str, ...]
    #: Extra Windows install paths, tried when PATH does not have it.
    windows_paths: tuple[str, ...] = ()
    #: Names the owner may use for it in chat.
    aliases: tuple[str, ...] = ()


_EDITOR_ROOTS = {
    'ProgramFiles': r'C:\Program Files',
    'ProgramFiles(x86)': r'C:\Program Files (x86)',
    'LocalAppData': None,
}


EDITORS = (
    EditorSpec(
        name='VS Code',
        command='code',
        capabilities=(CAP_OPEN_PROJECT, CAP_OPEN_FILE, CAP_RUN_TESTS),
        windows_paths=(r'Microsoft VS Code\Code.exe',),
        aliases=('vs code', 'vscode', 'code', 'விசு கோடு'),
    ),
    EditorSpec(
        name='Antigravity',
        command='antigravity',
        capabilities=(CAP_OPEN_PROJECT, CAP_OPEN_FILE),
        aliases=('antigravity', 'anti gravity'),
    ),
    EditorSpec(
        name='Visual Studio',
        command='devenv',
        capabilities=(CAP_OPEN_PROJECT, CAP_OPEN_FILE, CAP_BUILD),
        windows_paths=(r'Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.exe',
                       r'Microsoft Visual Studio\2022\Professional\Common7\IDE\devenv.exe',
                       r'Microsoft Visual Studio\2022\Enterprise\Common7\IDE\devenv.exe'),
        aliases=('visual studio', 'vs'),
    ),
    EditorSpec(
        name='Android Studio',
        command='studio64',
        capabilities=(CAP_OPEN_PROJECT, CAP_OPEN_FILE, CAP_BUILD),
        windows_paths=(r'Android\Android Studio\bin\studio64.exe',),
        aliases=('android studio', 'studio'),
    ),
    EditorSpec(
        name='IntelliJ IDEA',
        command='idea64',
        capabilities=(CAP_OPEN_PROJECT, CAP_OPEN_FILE, CAP_RUN_TESTS),
        windows_paths=(r'JetBrains\IntelliJ IDEA Community\bin\idea64.exe',
                       r'JetBrains\IntelliJ IDEA Ultimate\bin\idea64.exe'),
        aliases=('intellij', 'intellij idea', 'idea'),
    ),
    EditorSpec(
        name='PyCharm',
        command='pycharm64',
        capabilities=(CAP_OPEN_PROJECT, CAP_OPEN_FILE, CAP_RUN_TESTS),
        windows_paths=(r'JetBrains\PyCharm Community\bin\pycharm64.exe',
                       r'JetBrains\PyCharm Professional\bin\pycharm64.exe'),
        aliases=('pycharm',),
    ),
)

_BY_NAME = {spec.name: spec for spec in EDITORS}


def editor_names() -> list[str]:
    """Every editor JARVIS knows, in the order they are offered."""
    return [spec.name for spec in EDITORS]


def spec(name: str) -> EditorSpec:
    """Look up one editor by its display name."""
    try:
        return _BY_NAME[name]
    except KeyError:
        raise KeyError('Unknown editor.') from None


def find_editor(name: str):
    """The executable for an editor, or None when it is not installed.

    PATH is tried first, because a developer who installs an editor usually
    also puts it on PATH. The known Windows install locations come next, and
    a configured launcher path comes last.
    """
    try:
        found = _BY_NAME[name]
    except KeyError:
        return None
    path = shutil.which(found.command)
    if path:
        return Path(path)
    if sys.platform == 'win32':
        for relative in found.windows_paths:
            candidate = _windows_candidate(relative)
            if candidate is not None:
                return candidate
    return None


def _windows_candidate(relative: str):
    """Resolve a relative Windows install path against the known roots."""
    roots = []
    for name, default in _EDITOR_ROOTS.items():
        base = os.environ.get(name)
        if base:
            roots.append(Path(base))
        elif default:
            roots.append(Path(default))
    local = os.environ.get('LocalAppData')
    if local:
        roots.append(Path(local) / 'Programs')
    for root in roots:
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def resolve_launcher(command: str):
    """Resolve a configured launcher command to an executable, or None.

    The command may be a full path to an executable or the name of one on
    PATH. Nothing is run here; the owner approves the exact command first.
    """
    command = (command or '').strip()
    if not command:
        return None
    candidate = Path(command)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    return Path(shutil.which(command)) if shutil.which(command) else None


def editor_status(name: str, configured=None, language: str = '') -> dict:
    """What the interface shows about one editor.

    `configured` is an optional configured launcher: a dictionary with
    `name`, `command` and `capabilities`. A configured launcher is reported
    on its own, with the capabilities the owner declared, one by one.
    """
    if configured:
        command = configured.get('command', '')
        path = resolve_launcher(command)
        return {
            'name': configured.get('name', 'Custom editor'),
            'kind': 'configured',
            'command': command,
            'path': str(path) if path else None,
            'installed': path is not None,
            'capabilities': list(configured.get('capabilities', [])),
            'setup': '' if path else (
                (summary_labels(language)['setup_set_up'] + f' {name}: '
                 + summary_labels(language)['setup_not_found'])
                if language else f'Set up {name}: the command was not found.'),
        }
    try:
        found = spec(name)
    except KeyError:
        return {
            'name': name, 'kind': 'unknown', 'command': '', 'path': None,
            'installed': False, 'capabilities': [],
            'setup': (
                (summary_labels(language)['setup_needed'] + f' {name}: '
                 + summary_labels(language)['setup_choose'])
                if language else
                f'Setup needed for {name}: choose its executable in Settings.'),
        }
    path = find_editor(name)
    return {
        'name': found.name,
        'kind': 'known',
        'command': found.command,
        'path': str(path) if path else None,
        'installed': path is not None,
        'capabilities': list(found.capabilities),
        'setup': '' if path else (
            (summary_labels(language)['setup_needed'] + f' {found.name}: '
             + summary_labels(language)['setup_install'].format(command=found.command))
            if language else
            f'Setup needed for {found.name}: install it, or add "{found.command}" to PATH, '
            'or configure it as a launcher in Settings.'),
    }


def all_statuses(configured_launchers=None) -> list[dict]:
    """Every editor, known and configured, with its capabilities."""
    statuses = [editor_status(name) for name in editor_names()]
    for launcher in configured_launchers or []:
        statuses.append(editor_status(launcher.get('name', ''), launcher))
    return statuses


def open_project_in_editor(name: str, folder, configured=None):
    """Open a project folder in an editor.

    The editor is started with the folder as its argument, so the owner sees
    the real project, not a new empty window.

    The name is deliberately NOT "launch_editor". The desktop application
    already has a "launch_editor" for the video tools — CapCut, DaVinci
    Resolve and After Effects — which opens an executable. Two different
    things with the same name in one module means one of them silently stops
    working, so this one says exactly what it does.
    """
    status = editor_status(name, configured)
    if not status['installed']:
        raise ValueError(status['setup'] or f'{name} is not installed.')
    executable = status['path']
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError('The project folder no longer exists.')
    try:
        process = subprocess.Popen([str(executable), str(folder)], shell=False, close_fds=True,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except OSError:
        raise RuntimeError(f'{name} could not be started.') from None
    return f'{name} opened {folder} (process {process.pid}).'


def editor_from_text(text: str, configured_launchers=None):
    """The editor the owner named in a sentence, or None.

    A configured launcher wins over a known editor with the same name, because
    the owner configured it on purpose.
    """
    if not isinstance(text, str):
        return None
    lowered = text.casefold()
    best = None
    best_length = 0
    for launcher in configured_launchers or []:
        name = (launcher.get('name') or '').strip()
        if name and name.casefold() in lowered and len(name) > best_length:
            best, best_length = launcher.get('name'), len(name)
    for found in EDITORS:
        for alias in (found.name, *found.aliases):
            if alias.casefold() in lowered and len(alias) > best_length:
                best, best_length = found.name, len(alias)
    return best
