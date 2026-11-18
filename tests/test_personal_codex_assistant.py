"""Exercise the personal coding assistant: one chat sentence to a reviewable diff.

WHAT IS COVERED
    * The acceptance sentence selects the saved project, the editor and the
      change, in Tanglish.
    * The project is opened in the chosen editor.
    * The Codex task runs in an ISOLATED worktree, never in the owner's
      working folder, and the owner's uncommitted work is reported as
      protected.
    * The diff, the changed files and the test results reach the conversation.
    * A missing editor says "Setup needed".
    * A missing Codex CLI says what to do.
    * A declined action changes nothing.
    * A failed test is reported as failed, not as passed.
    * Emergency Stop cancels the work and it STAYS cancelled after Resume.
    * Opening a saved project and running its tests can be trusted routines,
      and are approved one by one when they are not.
"""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import subprocess
import time

import pytest
from PySide6.QtWidgets import QApplication

import desktop.app as desktop
from developer_studio.codex_task import CodexTask, TaskOutcome
from developer_studio.editors import editor_status
from developer_studio.intents import parse_coding_request
from developer_studio.projects import SavedProject

ACCEPTANCE = ('JARVIS, my project-a VS Code-la open panni login page validation fix pannu. '
              'Tests run panni result sollu.')


def git(folder, *args):
    return subprocess.run(
        ['git', '-C', str(folder), '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
         *args], capture_output=True, text=True, check=True)


@pytest.fixture
def project(tmp_path):
    """A small Git project with one committed file."""
    folder = tmp_path / 'project-a'
    folder.mkdir()
    git(folder, 'init', '-b', 'main')
    (folder / 'app.py').write_text('def login():\n    return True\n', encoding='utf-8')
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


def save_project(win, name='project-a', path=None, editor='VS Code', tests='pytest -q'):
    from developer_studio.projects import load_projects, save_projects
    projects = load_projects(win.store)
    projects.append(SavedProject(name=name, path=str(path), editor=editor, test_command=tests))
    save_projects(win.store, projects)


def fake_codex(monkeypatch, *, edit=True, fail_tests=False):
    """Replace the Codex CLI with one that edits a file in the worktree."""
    seen = {}

    def run(executable, project, prompt, check_cancelled, **kwargs):
        seen['project'] = project
        seen['prompt'] = prompt
        seen['sandbox'] = kwargs.get('sandbox')
        seen['cwd'] = kwargs.get('cwd')
        if edit:
            target = os.path.join(str(kwargs.get('cwd')), 'app.py')
            with open(target, 'w', encoding='utf-8') as handle:
                handle.write('def login():\n    return "checked"\n')
        return 'Codex changed app.py.'

    monkeypatch.setattr('developer_studio.codex_task.run_codex', run)
    # The CLI itself is not installed here; only the call is replaced.
    monkeypatch.setattr('developer_studio.codex_task.codex_executable',
                        lambda: '/usr/bin/true')
    return seen


def wait_for_test(win, app, seconds=8):
    """Wait for the test-run worker."""
    deadline = time.monotonic() + seconds
    while win.test_worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def wait_for(win, app, seconds=8):
    """Wait for the coding task worker, not the chat worker."""
    deadline = time.monotonic() + seconds
    while win.coding_worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def trust_opening(win):
    """The owner trusts opening this project, so only the change needs approval."""
    from developer_studio.projects import set_trusted_routine
    set_trusted_routine(win.store, 'open:project-a', True)


# ── reading the request ──────────────────────────────────────────────────────

def test_the_acceptance_sentence_selects_the_project_the_editor_and_the_change():
    projects = [SavedProject('project-a', '/tmp/project-a', 'VS Code', 'pytest -q')]
    request = parse_coding_request(ACCEPTANCE, projects, lambda text: 'VS Code')
    assert request.project == 'project-a'
    assert request.editor == 'VS Code'
    assert request.change == 'login page validation'
    assert request.open_project is True
    assert request.make_change is True
    assert request.run_tests is True
    assert request.question == ''


def test_a_sentence_without_a_project_stays_ordinary_chat():
    projects = [SavedProject('project-a', '/tmp/project-a', 'VS Code', 'pytest -q')]
    request = parse_coding_request('what is the weather today', projects, lambda text: '')
    assert request.project == ''
    assert request.is_coding_request is False


# ── the task ─────────────────────────────────────────────────────────────────

def test_the_task_runs_in_an_isolated_worktree_and_protects_uncommitted_work(
        tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        (project / 'app.py').write_text('def login():\n    return "mine"\n', encoding='utf-8')
        seen = fake_codex(monkeypatch)
        monkeypatch.setattr('developer_studio.codex_task.run_local_tests',
                            lambda folder, command, timeout=1800: ('passed', '2 passed'))
        task = CodexTask(SavedProject('project-a', str(project), 'VS Code', 'pytest -q'),
                         'login page validation',
                         test_command='pytest -q',
                         worktree_root=tmp_path / 'worktrees',
                         codex_path='/usr/bin/true')
        outcome = task.run()
        assert outcome.status == 'completed', outcome.message
        assert seen['cwd'] != str(project)
        assert 'login page validation' in seen['prompt']
        assert seen['sandbox'] == 'workspace-write'
        assert outcome.changed_files == ['app.py']
        assert 'app.py' in outcome.diff
        assert outcome.test_status == 'passed'
        # The owner's own uncommitted work is untouched.
        assert (project / 'app.py').read_text(encoding='utf-8') == \
            'def login():\n    return "mine"\n'
        assert outcome.protected
    finally:
        win.close()
        win.deleteLater()


def test_a_task_in_a_folder_that_is_not_a_git_repository_is_refused(tmp_path, monkeypatch):
    plain = tmp_path / 'plain'
    plain.mkdir()
    win, app = window(tmp_path, monkeypatch)
    try:
        task = CodexTask(SavedProject('plain', str(plain), 'VS Code', ''),
                         'fix the login', worktree_root=tmp_path / 'worktrees',
                         codex_path='/usr/bin/true')
        outcome = task.run()
        assert outcome.status == 'blocked'
        assert 'Git repository' in outcome.message
    finally:
        win.close()
        win.deleteLater()


def test_a_missing_codex_cli_says_what_to_do(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        task = CodexTask(SavedProject('project-a', str(project), 'VS Code', ''),
                         'fix the login', worktree_root=tmp_path / 'worktrees',
                         codex_path=None)
        task.codex_path = None
        monkeypatch.setattr('developer_studio.codex_task.codex_executable',
                            lambda: (_ for _ in ()).throw(
                                ValueError('Install Codex CLI, add it to PATH, sign in with '
                                           'codex login, and restart JARVIS.')))
        outcome = task.run()
        assert outcome.status == 'blocked'
        assert 'codex login' in outcome.message
    finally:
        win.close()
        win.deleteLater()


def test_a_failed_test_is_reported_as_failed(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        fake_codex(monkeypatch)
        monkeypatch.setattr('developer_studio.codex_task.run_local_tests',
                            lambda folder, command, timeout=1800: ('failed', '1 failed'))
        task = CodexTask(SavedProject('project-a', str(project), 'VS Code', 'pytest -q'),
                         'fix the login', test_command='pytest -q',
                         worktree_root=tmp_path / 'worktrees', codex_path='/usr/bin/true')
        outcome = task.run()
        assert outcome.status == 'completed'
        assert outcome.test_status == 'failed'
        assert '1 failed' in outcome.test_output
    finally:
        win.close()
        win.deleteLater()


# ── the chat flow ────────────────────────────────────────────────────────────

def test_the_chat_task_card_shows_the_project_the_change_and_the_steps(
        tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        request = win.coding_request(ACCEPTANCE)
        assert request is not None
        win.start_coding_task(request, ACCEPTANCE)
        card = win.chat_task_text.text()
        assert 'project-a' in card
        assert 'login page validation' in card
        # The card is written in the language the owner asked for, so both
        # wordings are accepted here.
        assert ('Open project-a in VS Code' in card
                or 'project-a திறக்க' in card)
        assert ('Ask Codex to' in card
                or 'Codex-க்கு சொல்ல' in card)
        assert win.chat_task_card.isVisible() or not win.chat_task_card.isHidden()
    finally:
        win.close()
        win.deleteLater()


def test_a_declined_action_changes_nothing(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        fake_codex(monkeypatch)
        request = win.coding_request(ACCEPTANCE)
        win.start_coding_task(request, ACCEPTANCE)
        win.finish_coding_approval(False)
        assert 'Declined' in win.transcript.toPlainText()
        assert win.coding_worker is None
    finally:
        win.close()
        win.deleteLater()


def test_the_conversation_keeps_the_result_visible(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        trust_opening(win)
        fake_codex(monkeypatch)
        monkeypatch.setattr('developer_studio.codex_task.run_local_tests',
                            lambda folder, command, timeout=1800: ('passed', '2 passed'))
        request = win.coding_request(ACCEPTANCE)
        win.start_coding_task(request, ACCEPTANCE)
        win.finish_coding_approval(True)
        wait_for(win, app)
        # The test command is approved on its own, separately.
        assert win.coding_pending is not None
        win.finish_coding_approval(True)
        wait_for_test(win, app)
        transcript = win.transcript.toPlainText()
        assert 'project-a' in transcript
        assert 'app.py' in transcript
        assert win.coding['outcome'] is not None
        assert win.coding['outcome'].changed_files == ['app.py']
    finally:
        win.close()
        win.deleteLater()


def test_emergency_stop_cancels_the_task_and_it_stays_cancelled(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        trust_opening(win)

        def refuse(executable, folder, prompt, check_cancelled, **kwargs):
            check_cancelled()
            return 'should not get here'

        monkeypatch.setattr('developer_studio.codex_task.run_codex', refuse)
        request = win.coding_request(ACCEPTANCE)
        win.start_coding_task(request, ACCEPTANCE)
        win.finish_coding_approval(True)
        win.stop()
        wait_for(win, app)
        outcome = win.coding.get('outcome')
        assert outcome is not None
        assert outcome.status == 'cancelled'
        # Resume must not revive it.
        win.resume()
        app.processEvents()
        assert win.coding['outcome'].status == 'cancelled'
    finally:
        win.close()
        win.deleteLater()


# ── editors and routines ─────────────────────────────────────────────────────

def test_a_missing_editor_says_setup_needed(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        state = editor_status('PyCharm')
        if state['installed']:
            pytest.skip('PyCharm is installed on this machine.')
        assert state['installed'] is False
        assert 'Setup needed' in state['setup']
        assert state['capabilities']
    finally:
        win.close()
        win.deleteLater()


def test_each_editor_shows_its_capabilities_individually():
    for name in ('VS Code', 'Visual Studio', 'Android Studio', 'IntelliJ IDEA', 'PyCharm'):
        state = editor_status(name)
        assert state['capabilities'], name
        assert 'open_project' in state['capabilities'], name


def test_a_trusted_routine_opens_the_project_without_asking(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        from developer_studio.projects import set_trusted_routine
        set_trusted_routine(win.store, 'open:project-a', True)
        opened = []
        monkeypatch.setattr(desktop, 'open_project_in_editor',
                            lambda name, folder, configured=None:
                            opened.append((name, str(folder))) or 'opened')
        request = win.coding_request(ACCEPTANCE)
        win.start_coding_task(request, ACCEPTANCE)
        assert opened and opened[0][0] == 'VS Code'
    finally:
        win.close()
        win.deleteLater()


def test_an_untrusted_routine_asks_first(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        opened = []
        monkeypatch.setattr(desktop, 'open_project_in_editor',
                            lambda name, folder, configured=None:
                            opened.append((name, str(folder))) or 'opened')
        request = win.coding_request(ACCEPTANCE)
        win.start_coding_task(request, ACCEPTANCE)
        assert opened == []
        assert 'Approve this task' in win.chat_task_text.text()
    finally:
        win.close()
        win.deleteLater()


# ── the settings page ────────────────────────────────────────────────────────

def test_the_saved_projects_page_lists_the_projects_and_the_editors(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=tmp_path)
        win.refresh_projects_page()
        assert win.projects_table.rowCount() == 1
        assert win.projects_table.item(0, 0).text() == 'project-a'
        status = win.editor_status.text()
        for name in ('VS Code', 'Visual Studio', 'Android Studio', 'IntelliJ IDEA', 'PyCharm'):
            assert name in status
        assert 'SETUP NEEDED' in status or 'installed' in status
    finally:
        win.close()
        win.deleteLater()


def test_the_assistant_language_is_remembered(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        from developer_studio.projects import assistant_language
        assert assistant_language(win.store) == 'ta'
        win.change_assistant_language('English')
        assert assistant_language(win.store) == 'en'
        win.change_assistant_language('Français (French)')
        assert assistant_language(win.store) == 'fr'
    finally:
        win.close()
        win.deleteLater()


def test_a_configured_launcher_is_remembered_and_reports_its_capabilities(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        win.launcher_name.setText('Fleet')
        win.launcher_command.setText(__import__('sys').executable)
        win.add_launcher()
        from developer_studio.projects import configured_launchers
        launchers = configured_launchers(win.store)
        assert launchers and launchers[0]['name'] == 'Fleet'
        state = editor_status('Fleet', launchers[0])
        assert state['kind'] == 'configured'
        assert state['installed'] is True
        assert state['capabilities'] == ['open_project', 'open_file']
    finally:
        win.close()
        win.deleteLater()
