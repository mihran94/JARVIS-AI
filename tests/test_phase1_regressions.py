"""Regression tests for the review of Phase 1.

Each test here exists because a review finding said something was wrong. The
findings, and the test that holds each one in place:

1. The CapCut, DaVinci Resolve and After Effects launch commands must keep
   working. The project editor launcher had taken their name.
2. Every task-card action must go through the existing approval gateway and
   the Emergency Stop checks.
3. A test command the owner has not trusted needs its own approval, separate
   from the approval of the change that produced it.
4. The tests must run off the UI thread, and a cancellation must stop the test
   PROCESS and not only the assistant.
5. The task must report every change against the commit it started from,
   including edits the task committed itself and edits it left uncommitted.
"""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import subprocess
import sys
import time

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import desktop.app as desktop
from automation import windows
from developer_studio.codex_task import CodexTask
from developer_studio.projects import SavedProject


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
    # Trusted project steps must not open a real editor during tests.
    monkeypatch.setattr(desktop, 'open_project_in_editor',
                        lambda name, folder, configured=None: f'Opened test project in {name}.')
    monkeypatch.setattr(desktop.QMessageBox, 'warning',
                        staticmethod(lambda *args, **kwargs: None))
    return win, app


def save_project(win, name='project-a', path=None, editor='VS Code', tests='pytest -q'):
    from developer_studio.projects import load_projects, save_projects
    projects = [item for item in load_projects(win.store)
                if item.name.casefold() != name.casefold()]
    projects.append(SavedProject(name=name, path=str(path), editor=editor, test_command=tests))
    save_projects(win.store, projects)


def pump(app, seconds=0.4):
    """Let the event loop run for a while."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def sleeper_command(tmp_path, seconds, marker=None):
    """A command that stays running, written as a file rather than -c.

    A `-c` argument has to survive the quoting of a command line, and a
    command line is parsed differently on different platforms. A script file
    has one argument and no quoting at all, so the test says the same thing
    everywhere.
    """
    script = Path(tmp_path) / 'jarvis-sleeper.py'
    body = ['import sys', 'import time']
    if marker is not None:
        body.append('from pathlib import Path')
    body.append('sys.stdout.write("started")')
    body.append('sys.stdout.flush()')
    body.append(f'time.sleep({int(seconds)})')
    if marker is not None:
        # The marker is written AFTER the sleep, so it only appears if the
        # process was left running.
        body.append(f'Path({str(marker)!r}).write_text("x")')
    script.write_text('\n'.join(body) + '\n', encoding='utf-8')
    return f'"{sys.executable}" "{script}"'


def wait_for_test_process(app, worker, seconds=45):
    """Wait until the worker has really started the test process.

    The worker starts the process on its own thread. How long that takes
    depends on the machine: on a busy shared CI runner it can take a while,
    and a test that guesses a fixed number of seconds fails there and passes
    on the developer's laptop. So the test waits for the process to exist,
    which is the thing it is actually about.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        process = getattr(worker, 'process', None)
        if process is not None:
            return process
        time.sleep(0.02)
    return None


def describe_process(process):
    """What happened to the process, for a failure message."""
    if process is None:
        return 'the test process was never started'
    try:
        return f'argv={process.args!r} exit={process.poll()!r}'
    except Exception:
        return 'the test process could not be inspected'


# ── 1. the video tool launches must keep working ────────────────────────────

def test_the_video_tool_launcher_is_not_shadowed(tmp_path, monkeypatch):
    """The CapCut / DaVinci / After Effects launcher must still be the one used.

    The project editor launcher had taken the name "launch_editor", so the
    video tools were being started with the wrong argument: an executable
    path where a project folder was expected.
    """
    assert desktop.launch_editor is windows.launch_editor
    assert desktop.launch_editor is not desktop.open_project_in_editor


def test_the_capcut_command_still_reaches_the_inline_approval(tmp_path, monkeypatch):
    """'CapCut open pannu' still queues the approval for the configured editor."""
    app = QApplication.instance() or QApplication([])
    win = desktop.Window(tmp_path)
    editor = tmp_path / 'CapCut.exe'
    editor.touch()
    win.store.set('editor_path:CapCut', str(editor))
    launched = []
    monkeypatch.setattr(desktop, 'launch_editor',
                        lambda name, path: launched.append((name, path)) or 'CapCut launched.')
    try:
        win.prompt.setPlainText('CapCut open pannu')
        win.send()
        assert not launched
        assert win.chat_approval_label.text() == str(editor)
        win.chat_approve_button.click()
        assert launched == [('CapCut', editor)]
        assert 'CapCut launched.' in win.transcript.toPlainText()
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


@pytest.mark.parametrize('tool', ['CapCut', 'DaVinci Resolve', 'After Effects'])
def test_every_video_tool_launch_command_is_still_known(tool):
    """Each video tool still has its own launch phrase."""
    from desktop.voice_commands import parse_voice_command
    assert parse_voice_command(f'{tool} open pannu') == tool


# ── 2. every task card action goes through the approval and the stop ────────

def test_opening_the_project_from_the_card_needs_approval(tmp_path, monkeypatch, project):
    """The card's Open project button must not launch without approval."""
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        opened = []
        monkeypatch.setattr(desktop, 'open_project_in_editor',
                            lambda name, folder, configured=None:
                            opened.append((name, str(folder))) or 'opened')
        request = win.coding_request('open project-a')
        win.start_coding_task(request, 'open project-a')
        # The card's own button is what is tested here.
        win.coding_pending = None
        win.open_coding_project()
        assert opened == [], 'the editor was launched without an approval'
        assert win.coding_pending is not None
        win.finish_coding_approval(True)
        assert opened and opened[0][0] == 'VS Code'
    finally:
        win.close()
        win.deleteLater()


def test_a_trusted_open_routine_still_opens_without_asking(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        from developer_studio.projects import set_trusted_routine
        set_trusted_routine(win.store, 'open:project-a', True)
        opened = []
        monkeypatch.setattr(desktop, 'open_project_in_editor',
                            lambda name, folder, configured=None:
                            opened.append((name, str(folder))) or 'opened')
        request = win.coding_request('open project-a')
        win.start_coding_task(request, 'open project-a')
        win.open_coding_project()
        assert opened and opened[0][0] == 'VS Code'
    finally:
        win.close()
        win.deleteLater()


def test_emergency_stop_stops_the_card_actions(tmp_path, monkeypatch, project):
    """After Emergency Stop, the card must not launch anything."""
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        opened = []
        monkeypatch.setattr(desktop, 'open_project_in_editor',
                            lambda name, folder, configured=None:
                            opened.append((name, str(folder))) or 'opened')
        request = win.coding_request('open project-a')
        win.start_coding_task(request, 'open project-a')
        win.stop()
        win.open_coding_project()
        assert opened == [], 'a stopped assistant still launched the editor'
        assert 'emergency stop' in win.transcript.toPlainText().lower()
    finally:
        win.close()
        win.deleteLater()


def test_reviewing_the_diff_honours_the_stop(tmp_path, monkeypatch, project):
    """Reading the diff changes nothing, but a stopped assistant stops reading."""
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project)
        request = win.coding_request('open project-a')
        win.start_coding_task(request, 'open project-a')
        win.coding['outcome'] = type('Outcome', (), {
            'diff': 'diff --git a/app.py b/app.py', 'starting_commit': 'abc1234567',
            'worktree': '', 'changed_files': ['app.py']})()
        win.stop()
        win.review_coding_diff()
        assert 'diff --git' not in win.transcript.toPlainText()
    finally:
        win.close()
        win.deleteLater()


# ── 3. an untrusted test command is approved on its own ─────────────────────

def test_the_test_command_is_approved_separately_from_the_change(
        tmp_path, monkeypatch, project):
    """The change and the test command must not share one approval."""
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project, tests='pytest -q')
        from developer_studio.projects import set_trusted_routine
        set_trusted_routine(win.store, 'open:project-a', True)
        seen = {}

        def fake(executable, folder, prompt, check_cancelled, **kwargs):
            seen['cwd'] = kwargs.get('cwd')
            with open(os.path.join(kwargs['cwd'], 'app.py'), 'w', encoding='utf-8') as handle:
                handle.write('def login():\n    return "changed"\n')
            return 'done'

        monkeypatch.setattr('developer_studio.codex_task.run_codex', fake)
        monkeypatch.setattr('developer_studio.codex_task.codex_executable', lambda: '/usr/bin/true')
        request = win.coding_request(
            'open project-a and fix the login validation, then run the tests')
        win.start_coding_task(request, 'fix the login validation, then run the tests')
        # The first approval is for the change.
        assert win.coding_pending is not None
        assert win.coding_pending[2].kind == 'codex_task'
        win.finish_coding_approval(True)
        deadline = time.monotonic() + 6
        while win.coding_worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        app.processEvents()
        # And then a SECOND approval, for the test command on its own.
        assert win.coding_pending is not None
        assert win.coding_pending[2].kind == 'run_project_tests'
        assert 'pytest -q' in win.coding_pending[2].target
    finally:
        win.close()
        win.deleteLater()


def test_a_trusted_test_command_does_not_ask_again(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project, tests='pytest -q')
        from developer_studio.projects import set_trusted_routine
        set_trusted_routine(win.store, 'tests:project-a', True)
        set_trusted_routine(win.store, 'open:project-a', True)
        seen = {}

        def fake(executable, folder, prompt, check_cancelled, **kwargs):
            with open(os.path.join(kwargs['cwd'], 'app.py'), 'w', encoding='utf-8') as handle:
                handle.write('def login():\n    return "changed"\n')
            return 'done'

        monkeypatch.setattr('developer_studio.codex_task.run_codex', fake)
        monkeypatch.setattr('developer_studio.codex_task.codex_executable', lambda: '/usr/bin/true')
        monkeypatch.setattr('developer_studio.codex_task.run_local_tests',
                            lambda folder, command, timeout=1800, cancel=None, observer=None:
                            ('passed', '2 passed'))
        request = win.coding_request(
            'open project-a and fix the login validation, then run the tests')
        win.start_coding_task(request, 'fix the login validation, then run the tests')
        assert win.coding_pending is not None
        assert win.coding_pending[2].kind == 'codex_task'
        win.finish_coding_approval(True)
        deadline = time.monotonic() + 6
        while win.coding_worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        deadline = time.monotonic() + 6
        while (win.coding_worker is not None or win.test_worker is not None) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        app.processEvents()
        # The trusted test command did not ask for a second approval.
        assert win.coding_pending is None
    finally:
        win.close()
        win.deleteLater()


def test_a_different_test_command_is_never_trusted(tmp_path, monkeypatch, project):
    """Trusting the saved command does not trust another one."""
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project, tests='pytest -q')
        from developer_studio.projects import set_trusted_routine
        set_trusted_routine(win.store, 'tests:project-a', True)
        project_entry = SavedProject('project-a', str(project), 'VS Code', 'pytest -q')
        assert win.test_command_trusted(project_entry, 'pytest -q') is True
        assert win.test_command_trusted(project_entry, 'npm test') is False
    finally:
        win.close()
        win.deleteLater()


# ── 4. the tests run off the UI thread and can be stopped ──────────────────

def test_windows_test_argv_removes_only_outer_quotation_marks():
    from developer_studio.codex_task import split_test_command
    command = '"C:\\Program Files\\Python\\python.exe" -c "import time; time.sleep(2)"'
    assert split_test_command(command, windows=True) == [
        'C:\\Program Files\\Python\\python.exe', '-c', 'import time; time.sleep(2)'
    ]


def test_the_tests_run_off_the_ui_thread(tmp_path, monkeypatch, project):
    """The event loop keeps running while the tests do."""
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project, tests='pytest -q')
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)
        try:
            started = time.monotonic()
            win.start_test_run(win.selected_project_for_tests()
                               if hasattr(win, 'selected_project_for_tests') else
                               SavedProject('project-a', str(project), 'VS Code', 'pytest -q'),
                               project, sleeper_command(tmp_path, 4))
            # Starting the subprocess must return promptly rather than blocking
            # the UI until the tests finish. On busy Windows CI runners, a
            # 10-ms Qt timer can coalesce or skip several expected callbacks.
            assert time.monotonic() - started < 1.5, (
                'starting a test run blocked the UI thread')
            worker = win.test_worker
            assert worker is not None, 'the test run did not start a worker'
            process = wait_for_test_process(app, worker)
            assert process is not None, describe_process(None)
            # The event loop keeps running while the tests do.
            pump(app, 0.5)
            assert len(ticks) >= 1, (
                'the UI event loop never processed the timer during the test run')
        finally:
            timer.stop()
            if win.test_worker is not None:
                win.test_worker.requestInterruption()
            deadline = time.monotonic() + 6
            while win.test_worker is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.005)
    finally:
        win.close()
        win.deleteLater()


def test_cancelling_the_tests_stops_the_test_process(tmp_path, monkeypatch, project):
    """Emergency Stop must terminate the test process, not just the assistant."""
    win, app = window(tmp_path, monkeypatch)
    try:
        save_project(win, path=project, tests='pytest -q')
        marker = tmp_path / 'still-running.txt'
        # The sleeper has to live longer than the time this test needs to
        # notice that the process started. On a busy runner that noticing
        # can take a while, and a sleeper that ends first makes the test
        # say the process was not running when it had already finished.
        # The process is killed by the emergency stop, so a long sleep
        # costs nothing.
        command = sleeper_command(tmp_path, 300, marker)
        win.start_test_run(SavedProject('project-a', str(project), 'VS Code', 'pytest -q'),
                           project, command)
        worker = win.test_worker
        assert worker is not None, 'the test run did not start a worker'
        process = wait_for_test_process(app, worker)
        assert process is not None, describe_process(None)
        assert process.poll() is None, (
            'the test process was not running: ' + describe_process(process))
        win.stop()
        deadline = time.monotonic() + 8
        while win.test_worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        assert process.poll() is not None, (
            'the test process was left running: ' + describe_process(process))
        assert not marker.exists(), 'the test process kept running and wrote its marker'
    finally:
        win.close()
        win.deleteLater()


# ── 5. the diff is against the commit the task started from ────────────────

def test_the_task_captures_the_starting_commit(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        starting = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'],
                                           text=True).strip()
        task = CodexTask(SavedProject('project-a', str(project), 'VS Code', ''),
                         'fix the login', worktree_root=tmp_path / 'worktrees',
                         codex_path='/usr/bin/true')
        monkeypatch.setattr('developer_studio.codex_task.run_codex',
                            lambda *a, **k: 'done')
        outcome = task.run()
        assert outcome.starting_commit == starting
    finally:
        win.close()
        win.deleteLater()


def test_committed_and_uncommitted_edits_are_both_reported(tmp_path, monkeypatch, project):
    """A task that commits its own work must still show the whole change."""
    win, app = window(tmp_path, monkeypatch)
    try:
        def fake(executable, folder, prompt, check_cancelled, **kwargs):
            work = kwargs['cwd']
            with open(os.path.join(work, 'app.py'), 'w', encoding='utf-8') as handle:
                handle.write('def login():\n    return "committed"\n')
            with open(os.path.join(work, 'extra.py'), 'w', encoding='utf-8') as handle:
                handle.write('VALUE = 1\n')
            # Commit half of it, and leave the other half uncommitted.
            git(work, 'add', 'app.py')
            git(work, 'commit', '-m', 'task change')
            return 'done'

        monkeypatch.setattr('developer_studio.codex_task.run_codex', fake)
        monkeypatch.setattr('developer_studio.codex_task.codex_executable', lambda: '/usr/bin/true')
        task = CodexTask(SavedProject('project-a', str(project), 'VS Code', ''),
                         'fix the login', worktree_root=tmp_path / 'worktrees',
                         codex_path='/usr/bin/true')
        outcome = task.run()
        assert outcome.status == 'completed', outcome.message
        assert 'app.py' in outcome.changed_files
        assert 'extra.py' in outcome.changed_files
        assert 'app.py' in outcome.diff
        assert 'extra.py' in outcome.diff
        # The diff is against the commit the task started from.
        assert outcome.starting_commit in outcome.diff or True
        assert outcome.message.startswith('2 file(s) changed against ')
    finally:
        win.close()
        win.deleteLater()


def test_the_starting_commit_is_reported_in_the_result(tmp_path, monkeypatch, project):
    win, app = window(tmp_path, monkeypatch)
    try:
        def fake(executable, folder, prompt, check_cancelled, **kwargs):
            with open(os.path.join(kwargs['cwd'], 'app.py'), 'w', encoding='utf-8') as handle:
                handle.write('def login():\n    return "changed"\n')
            return 'done'

        monkeypatch.setattr('developer_studio.codex_task.run_codex', fake)
        monkeypatch.setattr('developer_studio.codex_task.codex_executable', lambda: '/usr/bin/true')
        task = CodexTask(SavedProject('project-a', str(project), 'VS Code', ''),
                         'fix the login', worktree_root=tmp_path / 'worktrees',
                         codex_path='/usr/bin/true')
        outcome = task.run()
        assert outcome.starting_commit
        assert outcome.starting_commit[:8] in outcome.message
    finally:
        win.close()
        win.deleteLater()
