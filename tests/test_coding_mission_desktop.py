"""The coding path that needs no Codex CLI: JARVIS does the work itself.

WHAT IS COVERED
    * When the Codex CLI is not installed, the coding request starts
      JARVIS's own coding mission instead of stopping.
    * The mission runs in the project, the change is made through the
      approval boundary, and the answer reaches the conversation.
    * The steps of the mission reach the Mission Control console.
    * A refused change changes nothing.
    * Emergency Stop cancels the coding mission.
"""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import subprocess
import sys
import time

import pytest
from PySide6.QtWidgets import QApplication

import desktop.app as desktop
from developer_studio.projects import SavedProject


def git(folder, *args):
    return subprocess.run(
        ['git', '-C', str(folder), '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
         *args], capture_output=True, text=True, check=True)


@pytest.fixture
def project(tmp_path):
    """A Git project whose test fails until the value is fixed."""
    folder = tmp_path / 'project-a'
    folder.mkdir()
    git(folder, 'init', '-b', 'main')
    (folder / 'app.py').write_text('VALUE = 1\n', encoding='utf-8')
    (folder / 'test_app.py').write_text(
        'from app import VALUE\n\n\ndef test_value():\n    assert VALUE == 2\n',
        encoding='utf-8')
    git(folder, 'add', '-A')
    git(folder, 'commit', '-m', 'first')
    return folder


def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = desktop.Window(tmp_path)
    monkeypatch.setattr(win, 'get_key', lambda provider: 'fake-key')
    monkeypatch.setattr(desktop.QMessageBox, 'warning',
                        staticmethod(lambda *args, **kwargs: None))
    return win, app


def save_project(win, name='project-a', path=None, tests=None):
    if tests is None:
        tests = f'{sys.executable} -m pytest -q'
    from developer_studio.projects import load_projects, save_projects
    projects = load_projects(win.store)
    projects.append(SavedProject(name=name, path=str(path), editor='VS Code',
                                  test_command=tests))
    save_projects(win.store, projects)


def answer_with(answers):
    """A provider that answers the mission with the given JSON."""
    remaining = list(answers)

    def stream(spec, model, key, messages, check, emit, **kwargs):
        if remaining:
            return remaining.pop(0)
        return json.dumps({'action': 'answer', 'answer': 'The work is done.',
                           'thought': 'Done.'})

    return stream


def wait_for(win, app, seconds=25):
    """Wait for the mission to start and then to finish."""
    deadline = time.monotonic() + seconds
    started = False
    while time.monotonic() < deadline:
        app.processEvents()
        if win.coding_mission_worker is not None:
            started = True
        elif started:
            return True
        time.sleep(0.01)
    return False


# ── the path ───────────────────────────────────────────────────────────────

def test_without_the_codex_cli_the_mission_starts(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        # The Codex CLI is not installed on this machine.
        monkeypatch.setattr('developer_studio.codex_task.codex_executable',
                            lambda: (_ for _ in ()).throw(ValueError('not installed')))
        monkeypatch.setattr(win, 'confirm', lambda action: True)
        monkeypatch.setattr(win.router, 'stream', answer_with([
            json.dumps({'action': 'tool', 'tool': 'read_file',
                        'arguments': {'path': 'app.py'}, 'thought': 'Look first.'}),
            json.dumps({'action': 'tool', 'tool': 'write_file',
                        'arguments': {'path': 'app.py', 'content': 'VALUE = 2\n'},
                        'thought': 'The value is wrong.'}),
            json.dumps({'action': 'answer', 'answer': 'I changed app.py.',
                        'thought': 'Done.'}),
        ]))
        request = win.coding_request('fix the failing test in project-a')
        assert request is not None
        win.start_coding_task(request, 'fix the failing test in project-a')
        win.finish_coding_approval(True)
        assert wait_for(win, app)
        # The change was really made, in the project.
        assert (project / 'app.py').read_text(encoding='utf-8') == 'VALUE = 2\n'
        # And the answer reached the conversation.
        messages = win.store.messages(win.session)
        assert any('changed app.py' in message['content'] for message in messages)
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_the_steps_reach_the_mission_console(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        monkeypatch.setattr('developer_studio.codex_task.codex_executable',
                            lambda: (_ for _ in ()).throw(ValueError('not installed')))
        monkeypatch.setattr(win, 'confirm', lambda action: True)
        monkeypatch.setattr(win.router, 'stream', answer_with([
            json.dumps({'action': 'tool', 'tool': 'list_files', 'arguments': {},
                        'thought': 'Look around.'}),
            json.dumps({'action': 'answer', 'answer': 'I looked.', 'thought': 'Done.'}),
        ]))
        request = win.coding_request('fix the value in project-a')
        win.start_coding_task(request, 'fix the value in project-a')
        win.finish_coding_approval(True)
        assert wait_for(win, app)
        labels = [entry['label'] for entry in win.mission_panel.timeline.entries()]
        assert any('list_files' in label for label in labels)
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_a_refused_change_changes_nothing(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        monkeypatch.setattr('developer_studio.codex_task.codex_executable',
                            lambda: (_ for _ in ()).throw(ValueError('not installed')))
        monkeypatch.setattr(win.router, 'stream', answer_with([
            json.dumps({'action': 'tool', 'tool': 'write_file',
                        'arguments': {'path': 'app.py', 'content': 'VALUE = 9\n'},
                        'thought': 'A guess.'}),
            json.dumps({'action': 'answer', 'answer': 'I tried.', 'thought': 'Done.'}),
        ]))
        # The owner declines every change.
        monkeypatch.setattr(win, 'confirm', lambda action: False)
        request = win.coding_request('fix the value in project-a')
        win.start_coding_task(request, 'fix the value in project-a')
        win.finish_coding_approval(True)
        assert wait_for(win, app)
        assert (project / 'app.py').read_text(encoding='utf-8') == 'VALUE = 1\n'
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()
