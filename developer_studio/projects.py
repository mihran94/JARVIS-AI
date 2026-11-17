"""Saved projects: the folders JARVIS works in and the editor each one uses.

WHAT THIS IS
    The owner saves each project folder once, with the editor they work in and
    the local test command for it. After that, a chat request only has to name
    the project, and JARVIS knows where to go and what "run the tests" means
    for it.

WHY THE PROJECT IS NAMED
    A folder path is not something a person says out loud. "project-a" is. So
    the saved project has a short name, and the request names it.

WHAT IS STORED
    The name, the folder, the editor and the test command. Nothing secret,
    nothing about a provider, and no credentials. The credential store stays
    where it was.

WHAT THIS MODULE WILL NOT DO
    * It never runs anything. It only remembers and reports.
    * It never touches a folder that is not the one the owner saved.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess


#: Where the saved projects live in the settings store.
PROJECTS_KEY = 'saved_projects'
#: Where the owner's own launcher commands live.
LAUNCHERS_KEY = 'configured_launchers'
#: Where the trusted routine switches live.
ROUTINES_KEY = 'trusted_routines'
#: Where the assistant language preference lives.
LANGUAGE_KEY = 'assistant_language'


@dataclass(frozen=True)
class SavedProject:
    """One project the owner saved."""

    name: str
    path: str
    editor: str = 'VS Code'
    test_command: str = ''

    @property
    def folder(self) -> Path:
        return Path(self.path)

    @property
    def exists(self) -> bool:
        return self.folder.is_dir()


def load_projects(store) -> list[SavedProject]:
    """Every saved project, in the order the owner saved them."""
    raw = store.get(PROJECTS_KEY) or []
    projects = []
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get('name', '')).strip()
            path = str(entry.get('path', '')).strip()
            if not name or not path:
                continue
            projects.append(SavedProject(
                name=name,
                path=path,
                editor=str(entry.get('editor', 'VS Code')).strip() or 'VS Code',
                test_command=str(entry.get('test_command', '')).strip(),
            ))
    return projects


def save_projects(store, projects) -> None:
    """Remember the saved projects."""
    store.set(PROJECTS_KEY, [
        {'name': project.name, 'path': project.path, 'editor': project.editor,
         'test_command': project.test_command}
        for project in projects
    ])


def find_project(projects, name: str):
    """The saved project with that name, or None.

    The match is case-insensitive and ignores spaces and dashes, because a
    person saying "project A" means the project saved as "project-a".
    """
    if not isinstance(name, str):
        return None
    wanted = _normalise(name)
    if not wanted:
        return None
    for project in projects:
        if _normalise(project.name) == wanted:
            return project
    return None


def _normalise(text: str) -> str:
    return ''.join(char for char in str(text or '').casefold() if char.isalnum())


def project_status(project, editor_status_for=None) -> dict:
    """What the interface shows about one saved project."""
    folder = project.folder
    exists = folder.is_dir()
    status = {
        'name': project.name,
        'path': project.path,
        'editor': project.editor,
        'test_command': project.test_command,
        'exists': exists,
        'git': False,
        'dirty': False,
        'uncommitted': 0,
        'setup': '' if exists else 'The project folder is not there any more.',
    }
    if not exists:
        return status
    if _is_git_repo(folder):
        status['git'] = True
        changed = _git_status(folder)
        status['dirty'] = bool(changed)
        status['uncommitted'] = len(changed)
    if editor_status_for is not None:
        editor = editor_status_for(project.editor)
        status['editor_installed'] = editor['installed']
        status['editor_setup'] = editor['setup']
    return status


def _git_command(folder, *args):
    try:
        result = subprocess.run(['git', '-C', str(folder), *args], capture_output=True,
                                text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    return result.stdout


def _is_git_repo(folder: Path) -> bool:
    output = _git_command(folder, 'rev-parse', '--is-inside-work-tree')
    return bool(output and output.strip() == 'true')


def _git_status(folder: Path) -> list[str]:
    output = _git_command(folder, 'status', '--porcelain')
    if not output:
        return []
    return [line for line in output.splitlines() if line.strip()]


def configured_launchers(store) -> list[dict]:
    """The owner's own launcher commands."""
    raw = store.get(LAUNCHERS_KEY) or []
    launchers = []
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get('name', '')).strip()
            command = str(entry.get('command', '')).strip()
            if not name or not command:
                continue
            capabilities = entry.get('capabilities')
            launchers.append({
                'name': name,
                'command': command,
                'capabilities': [str(item) for item in capabilities] if isinstance(capabilities, list) else [],
            })
    return launchers


def save_configured_launchers(store, launchers) -> None:
    """Remember the owner's launcher commands."""
    store.set(LAUNCHERS_KEY, [
        {'name': item.get('name', ''), 'command': item.get('command', ''),
         'capabilities': list(item.get('capabilities', []))}
        for item in launchers
    ])


def trusted_routines(store) -> dict:
    """Which routine actions the owner has already approved.

    A routine is an action the owner allows WITHOUT asking again: opening a
    saved project, or running that project's configured local tests. Nothing
    else is a routine.
    """
    raw = store.get(ROUTINES_KEY) or {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): bool(value) for key, value in raw.items()}


def set_trusted_routine(store, key: str, enabled: bool) -> None:
    """Turn one trusted routine on or off."""
    routines = trusted_routines(store)
    routines[str(key)] = bool(enabled)
    store.set(ROUTINES_KEY, routines)


def routine_allowed(store, key: str) -> bool:
    """True when the owner has approved this routine for this project."""
    return bool(trusted_routines(store).get(str(key)))


def assistant_language(store) -> str:
    """The language the owner prefers for spoken and written replies."""
    value = str(store.get(LANGUAGE_KEY) or '').strip().casefold()
    return value if value in ('en', 'ta', 'fr') else 'ta'


def set_assistant_language(store, language: str) -> None:
    """Remember the assistant language."""
    value = str(language or '').strip().casefold()
    if value not in ('en', 'ta', 'fr'):
        raise ValueError('Choose English, தமிழ் or Français.')
    store.set(LANGUAGE_KEY, value)


def project_root_name(project: SavedProject) -> str:
    """The folder name of a project, for display."""
    try:
        return project.folder.name
    except (OSError, ValueError):
        return project.name


def expand_user(path: str) -> str:
    """Expand a saved folder path for this machine."""
    return os.path.expandvars(os.path.expanduser(str(path or '')))
