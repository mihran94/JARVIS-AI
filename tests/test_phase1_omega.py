"""Phase 1 blockers, proved on the JARVIS Omega tree.

These tests are the second round of Phase 1 review findings, plus the checks
that the Omega desktop modes survive the personal coding assistant.

THE FINDINGS
1. Task-card actions go through the approval gateway and the Emergency Stop.
2. An untrusted test command is approved on its own.
3. The tests run off the UI thread, and a stop ends the test PROCESS.
4. The launchers for software and for coding editors stay separate.
5. The diff is against the commit the task started from.
6. The task, its status, its test result and its worktree path are recorded in
   the task history.
7. A failed test is visible in the final result.
8. An active task and a pending approval are not overwritten by a new chat
   request.
9. Emergency Stop cancels the job, and Resume does not restart it.
10. The Omega desktop modes and settings still work.
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
from developer_studio.codex_task import CodexTask
from developer_studio.projects import SavedProject, set_trusted_routine


def git(folder, *args):
    return subprocess.run(
        ['git', '-C', str(folder), '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
         *args], capture_output=True, text=True, check=True)


@pytest.fixture
def project(tmp_path):
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
    projects = [item for item in load_projects(win.store)
                if item.name.casefold() != name.casefold()]
    projects.append(SavedProject(name=name, path=str(path), editor=editor, test_command=tests))
    save_projects(win.store, projects)


def fake_codex(monkeypatch):
    def run(executable, project, prompt, check_cancelled, **kwargs):
        with open(os.path.join(kwargs['cwd'], 'app.py'), 'w', encoding='utf-8') as handle:
            handle.write('def login():\n    return "changed"\n')
        return 'Codex changed app.py.'

    monkeypatch.setattr('developer_studio.codex_task.run_codex', run)
    monkeypatch.setattr('developer_studio.codex_task.codex_executable', lambda: '/usr/bin/true')


def wait_for_coding(win, app, seconds=8):
    deadline = time.monotonic() + seconds
    while win.coding_worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def wait_for_test(win, app, seconds=8):
    deadline = time.monotonic() + seconds
    while win.test_worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def run_a_task(win, app, monkeypatch, project, *, test_status='passed'):
    """Drive one full task: open, change, tests. Returns the history row."""
    save_project(win, path=project)
    set_trusted_routine(win.store, 'open:project-a', True)
    fake_codex(monkeypatch)
    monkeypatch.setattr('developer_studio.codex_task.run_local_tests',
                        lambda folder, command, timeout=1800, cancel=None, observer=None:
                        (test_status, '2 passed' if test_status == 'passed' else '1 failed'))
    request = win.coding_request(
        'open project-a and fix the login validation, then run the tests')
    win.start_coding_task(request, 'open project-a and fix the login validation')
    win.finish_coding_approval(True)
    wait_for_coding(win, app)
    if win.coding_pending is not None:
        win.finish_coding_approval(True)
    wait_for_test(win, app)
    rows = [row for row in win.store.tasks() if row['kind'] == 'codex_task']
    return rows[0] if rows else None


# ── 6. the task is recorded in the task history ────────────────────────────

def test_the_task_is_recorded_in_the_task_history(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        row = run_a_task(win, app, monkeypatch, project)
        assert row is not None, 'the task was not recorded in the history'
        assert row['status'] == 'completed'
        assert 'tests=passed' in row['detail']
        assert 'worktree=' in row['detail']
        assert 'from=' in row['detail']
        # The history page shows the same row.
        win.open_section('Task History')
        app.processEvents()
        assert win.history.rowCount() >= 1
    finally:
        win.close()
        win.deleteLater()


def test_the_history_row_is_written_while_the_task_runs(tmp_path, monkeypatch, project):
    """An interrupted task still leaves a trace."""
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        request = win.coding_request('open project-a')
        win.start_coding_task(request, 'open project-a')
        rows = [row for row in win.store.tasks() if row['kind'] == 'codex_task']
        assert rows and rows[0]['status'] == 'running'
    finally:
        win.close()
        win.deleteLater()


# ── 7. a failed test is visible in the final result ────────────────────────

def test_a_failed_test_is_visible_in_the_final_result(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        row = run_a_task(win, app, monkeypatch, project, test_status='failed')
        transcript = win.transcript.toPlainText()
        # The report is now written in the language the owner asked for, so
        # both wordings are accepted here.
        assert ('Tests: failed' in transcript
                or 'பரிட்சை முடிவு: failed' in transcript), transcript[-400:]
        assert row is not None
        assert row['status'] == 'failed'
        assert 'tests=failed' in row['detail']
    finally:
        win.close()
        win.deleteLater()


# ── 8. an active task is not overwritten by a new request ─────────────────

def test_a_new_request_does_not_overwrite_a_running_task(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        set_trusted_routine(win.store, 'open:project-a', True)
        fake_codex(monkeypatch)
        request = win.coding_request('open project-a and fix the login validation')
        win.start_coding_task(request, 'fix the login validation')
        first = win.coding
        # A second request arrives while the first task is waiting.
        second = win.coding_request('open project-a and fix the logout validation')
        assert second is not None
        win.start_coding_task(second, 'fix the logout validation')
        assert win.coding is first, 'the running task was overwritten'
        assert 'already running' in win.transcript.toPlainText()
    finally:
        win.close()
        win.deleteLater()


def test_a_pending_approval_is_not_overwritten_by_a_new_request(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        request = win.coding_request('open project-a and fix the login validation')
        win.start_coding_task(request, 'fix the login validation')
        pending = win.coding_pending
        assert pending is not None
        second = win.coding_request('open project-a and fix the logout validation')
        win.start_coding_task(second, 'fix the logout validation')
        assert win.coding_pending is pending, 'the pending approval was lost'
    finally:
        win.close()
        win.deleteLater()


def test_a_new_chat_does_not_orphan_a_running_task(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        request = win.coding_request('open project-a')
        win.start_coding_task(request, 'open project-a')
        session = win.session
        win.new_chat()
        assert win.session == session, 'the conversation changed under a running task'
    finally:
        win.close()
        win.deleteLater()


# ── 9. Stop cancels the job, and Resume does not restart it ───────────────

def test_stop_cancels_the_task_and_resume_does_not_restart_it(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        set_trusted_routine(win.store, 'open:project-a', True)

        def refuse(executable, folder, prompt, check_cancelled, **kwargs):
            check_cancelled()
            return 'should not get here'

        monkeypatch.setattr('developer_studio.codex_task.run_codex', refuse)
        request = win.coding_request('open project-a and fix the login validation')
        win.start_coding_task(request, 'fix the login validation')
        win.finish_coding_approval(True)
        win.stop()
        wait_for_coding(win, app)
        outcome = win.coding.get('outcome')
        assert outcome is not None
        assert outcome.status == 'cancelled'
        rows = [row for row in win.store.tasks() if row['kind'] == 'codex_task']
        assert rows and rows[0]['status'] == 'cancelled'
        # Resume must not bring it back.
        win.resume()
        app.processEvents()
        assert win.coding['outcome'].status == 'cancelled'
        assert win.coding_worker is None
    finally:
        win.close()
        win.deleteLater()


def test_the_approval_state_is_cleared_when_the_task_ends(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        request = win.coding_request('open project-a')
        win.start_coding_task(request, 'open project-a')
        assert win.coding_pending is not None
        win.finish_coding_approval(False)
        assert win.coding_pending is None
    finally:
        win.close()
        win.deleteLater()


# ── 10. Omega survives ─────────────────────────────────────────────────────

def test_the_omega_modes_are_still_there(tmp_path, monkeypatch):
    win, app = window(tmp_path, monkeypatch)
    try:
        from desktop.omega import MODES
        assert MODES == ('Omega', 'Island', 'Stealth')
        win.enable_omega(smoke=True)
        app.processEvents()
        assert win.omega is not None
        assert win.omega.mode in MODES
    finally:
        win.close()
        win.deleteLater()


def test_omega_still_shows_the_coding_work(tmp_path, monkeypatch, project):
    """The Omega presentation must show that a coding task is running."""
    win, app = window(tmp_path, monkeypatch)
    try:
        win.enable_omega(smoke=True)
        save_project(win, path=project)
        set_trusted_routine(win.store, 'open:project-a', True)
        fake_codex(monkeypatch)

        def slow(executable, folder, prompt, check_cancelled, **kwargs):
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                check_cancelled()
                time.sleep(0.02)
            return 'done'

        monkeypatch.setattr('developer_studio.codex_task.run_codex', slow)
        request = win.coding_request('open project-a and fix the login validation')
        win.start_coding_task(request, 'fix the login validation')
        win.finish_coding_approval(True)
        app.processEvents()
        assert win.omega.activity_label.text() == 'Coding', \
            'the Omega presentation did not show the coding task'
        win.stop()
        wait_for_coding(win, app)
        app.processEvents()
    finally:
        win.close()
        win.deleteLater()


def test_omega_still_receives_the_stop(tmp_path, monkeypatch):
    """Emergency Stop must still reach Omega."""
    win, app = window(tmp_path, monkeypatch)
    try:
        win.enable_omega(smoke=True)
        app.processEvents()
        win.stop()
        app.processEvents()
        assert win.policy.stopped is True
        win.resume()
        app.processEvents()
        assert win.policy.stopped is False
    finally:
        win.close()
        win.deleteLater()


# ── the software launchers and the coding editors stay separate ────────────

def test_the_software_and_coding_launchers_are_separate():
    from automation import windows
    from developer_studio import editors
    assert desktop.launch_editor is windows.launch_editor
    assert desktop.open_project_in_editor is editors.open_project_in_editor
    assert desktop.launch_editor is not desktop.open_project_in_editor


@pytest.mark.parametrize('tool', ['CapCut', 'DaVinci Resolve', 'After Effects'])
def test_the_software_launch_commands_still_work(tool):
    from desktop.voice_commands import parse_voice_command
    assert parse_voice_command(f'{tool} open pannu') == tool


def test_vs_code_still_opens_the_saved_project(tmp_path, monkeypatch, project):
    """The coding editor opens the project FOLDER."""
    win, app = window(tmp_path, monkeypatch)
    try:
        opened = []
        monkeypatch.setattr(desktop, 'open_project_in_editor',
                            lambda name, folder, configured=None:
                            opened.append((name, str(folder))) or 'opened')
        save_project(win, path=project, editor='VS Code')
        set_trusted_routine(win.store, 'open:project-a', True)
        request = win.coding_request('open project-a')
        win.start_coding_task(request, 'open project-a')
        assert opened == [('VS Code', str(project))]
    finally:
        win.close()
        win.deleteLater()


def test_a_configured_coding_editor_opens_the_saved_project(tmp_path, monkeypatch, project):
    """A launcher the owner configured opens the project too."""
    win, app = window(tmp_path, monkeypatch)
    try:
        opened = []
        monkeypatch.setattr(desktop, 'open_project_in_editor',
                            lambda name, folder, configured=None:
                            opened.append((name, str(folder), configured)) or 'opened')
        from developer_studio.projects import save_configured_launchers
        save_configured_launchers(win.store, [
            {'name': 'Fleet', 'command': '/usr/bin/true', 'capabilities': ['open_project']}])
        save_project(win, path=project, editor='Fleet')
        set_trusted_routine(win.store, 'open:project-a', True)
        request = win.coding_request('open project-a')
        win.start_coding_task(request, 'open project-a')
        assert opened and opened[0][0] == 'Fleet'
        assert opened[0][1] == str(project)
        assert opened[0][2]['command'] == '/usr/bin/true'
    finally:
        win.close()
        win.deleteLater()
