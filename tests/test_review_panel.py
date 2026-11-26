"""The review screen, and the always-on session.

WHAT IS COVERED
    * A prepared revision is shown with its diff and its test results.
    * Apply is disabled when the tests failed, and the screen says why.
    * Approving selects that exact revision and keeps the previous one.
    * Rejecting leaves the running version alone.
    * Closing the window keeps JARVIS in the tray when the owner asked for
      that, and the tray can pause and exit.
    * Starting at sign-in is a Windows setting, and it is off by default.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import sqlite3

import pytest
from PySide6.QtWidgets import QApplication

from core.candidates import Candidate, content_digest, read_candidate, store_prepared, write_candidate
from core.updates import read_state

REVISION = 'c' * 40
FILES = {'requirements.txt': b'pinned==1\n', 'main.py': b'new code',
         'core/store.py': b'stable database', 'desktop/app.py': b'new UI'}


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / 'install'
    for name, content in FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if name != 'main.py' else b'original code')
    history = tmp_path / 'history.sqlite3'
    with sqlite3.connect(history) as db:
        db.execute('CREATE TABLE history (message TEXT)')
    monkeypatch.setenv('JARVIS_INSTALL_ROOT', str(root))
    return root, history


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    from desktop.app import Window
    win = Window(tmp_path / 'user')
    yield win, app
    win.close()
    win.deleteLater()
    app.processEvents()


def prepare(root, *, status='passed'):
    store_prepared(root, REVISION, FILES)
    candidate = Candidate(
        revision=REVISION, digest=content_digest(FILES), base='base', changed=('main.py',),
        tests={'status': status, 'summary': '3 passed' if status == 'passed' else '1 failed'},
        prepared_at='2026-01-01 00:00 UTC')
    write_candidate(root, candidate)
    return candidate


def review_panel(window):
    widget = window.section_widget('Review changes')
    from PySide6.QtWidgets import QScrollArea
    return widget.widget() if isinstance(widget, QScrollArea) else widget


# ── the review screen ────────────────────────────────────────────────────────

def test_a_prepared_revision_is_shown_with_its_diff_and_tests(installation, window):
    root, history = installation
    win, app = window
    prepare(root)
    panel = review_panel(win)
    panel.refresh()
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 2).text() == REVISION[:12]
    diff = panel.diff.toPlainText()
    assert 'main.py' in diff
    # The diff is a real diff, not only a list of names.
    assert '--- a/main.py' in diff
    assert '+++ b/main.py' in diff
    assert '-original code' in diff
    assert '+new code' in diff
    assert 'Tests: passed' in panel.tests.toPlainText()
    assert panel.approve_button.isEnabled()


def test_apply_is_disabled_when_the_tests_failed(installation, window):
    root, history = installation
    win, app = window
    prepare(root, status='failed')
    panel = review_panel(win)
    panel.refresh()
    assert panel.approve_button.isEnabled() is False
    assert 'Apply is disabled' in panel.tests.toPlainText()
    assert 'failed' in panel.tests.toPlainText()


def test_approving_selects_the_revision_and_keeps_the_previous_one(installation, window):
    root, history = installation
    win, app = window
    prepare(root)
    panel = review_panel(win)
    panel.refresh()
    win.confirm = lambda action: True
    panel.approve()
    state = read_state(root)
    assert state['active'] != 'base'
    assert state['previous'] == 'base'
    assert read_candidate(root) is None


def test_rejecting_leaves_the_running_version_alone(installation, window):
    root, history = installation
    win, app = window
    prepare(root)
    panel = review_panel(win)
    panel.refresh()
    panel.reject()
    assert read_state(root)['active'] == 'base'
    assert read_candidate(root) is None


def test_nothing_is_waiting_for_review_at_the_start(installation, window):
    root, history = installation
    win, app = window
    panel = review_panel(win)
    panel.refresh()
    assert panel.table.rowCount() == 0
    assert panel.approve_button.isEnabled() is False


# ── the always-on session ────────────────────────────────────────────────────

def test_closing_the_window_keeps_jarvis_in_the_tray_when_it_is_asked(installation, window,
                                                                       monkeypatch):
    root, history = installation
    win, app = window
    from types import SimpleNamespace

    class FakeTray:
        def __init__(self, parent):
            self.visible = True
            self.activated = SimpleNamespace(connect=lambda callback: None)

        def setIcon(self, icon):
            pass

        def setToolTip(self, tooltip):
            pass

        def setContextMenu(self, menu):
            pass

        def show(self):
            self.visible = True

        def isVisible(self):
            return self.visible

    from desktop.tray import BackgroundControls
    win.background_controls = BackgroundControls(win, tray_available=True, tray_factory=FakeTray)
    win.store.set('keep_running_in_tray', True)
    win.show()
    app.processEvents()
    win.close()
    win.deleteLater()
    app.processEvents()
    # The window went away, but JARVIS is still running in the tray.
    assert win.isVisible() is False
    assert win.background_controls.tray.isVisible()


def test_closing_the_window_ends_jarvis_when_the_tray_is_not_asked_for(installation, window):
    root, history = installation
    win, app = window
    win.store.set('keep_running_in_tray', False)
    win.show()
    app.processEvents()
    win.close()
    win.deleteLater()
    app.processEvents()
    assert win.isVisible() is False


def test_starting_at_sign_in_is_a_windows_setting_and_is_off_by_default(tmp_path):
    from desktop import startup
    if startup.supported():
        pytest.skip('This machine is Windows, so the setting is real here.')
    assert startup.start_at_signin_enabled() is False
    with pytest.raises(startup.StartupError):
        startup.set_start_at_signin(True)


def test_the_start_at_sign_in_command_is_the_same_launcher(tmp_path, monkeypatch):
    from desktop import startup
    root = tmp_path / 'install'
    (root / 'scripts').mkdir(parents=True)
    (root / 'scripts' / 'launch.py').touch()
    monkeypatch.setenv('JARVIS_INSTALL_ROOT', str(root))
    command = startup.startup_command()
    assert 'launch.py' in command
    assert command.startswith('"')


def test_downloaded_tests_require_permission(installation, window, monkeypatch):
    root, _ = installation
    win, _ = window
    from dataclasses import replace

    candidate = replace(prepare(root), tests={})
    write_candidate(root, candidate)
    panel = review_panel(win)
    panel.refresh()
    requests = []
    approvals = []
    monkeypatch.setattr(win.release_checker, 'start_source_worker', lambda **args: requests.append(args))
    monkeypatch.setattr('desktop.app.QMessageBox.warning', lambda *args: None)
    win.confirm = lambda action: approvals.append(action) or False
    assert panel.test_button.isEnabled()
    assert not panel.approve_button.isEnabled()
    panel.test_button.click()
    assert not requests
    assert approvals[0].digest == candidate.digest
    win.confirm = lambda action: True
    panel.test_button.click()
    assert requests == [{'candidate': candidate}]
    assert read_state(root)['active'] == 'base'


def test_local_approval_launches_reviewed_source_and_allows_rollback(installation, window, monkeypatch):
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    from core.coding_tasks import create, load, save
    from core.development import prepare_improvement
    from core.updates import rollback

    root, _ = installation
    win, _ = window
    base_source = Path(__file__).resolve().parents[1]
    (root / 'scripts').mkdir()
    shutil.copyfile(base_source / 'scripts/launch.py', root / 'scripts/launch.py')
    shutil.copyfile(base_source / 'core/updates.py', root / 'core/updates.py')
    (root / 'main.py').write_text('print("original code")\n', encoding='utf-8')

    def git(*args):
        subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)

    git('init')
    git('add', '-A')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-m', 'Base')

    task = create(win.store, 'Change launch marker', 'MiniMax')

    def make_change(worktree, provider, goal):
        (worktree / 'main.py').write_text('print("approved local code")\n', encoding='utf-8')

    item = prepare_improvement(root, root, task.goal, task.provider, task.ident,
                               change=make_change, test_command='python -c "print(1)"')
    save(win.store, item)
    panel = review_panel(win)
    panel.refresh()
    win.confirm = lambda action: False
    panel.approve()
    assert read_state(root)['active'] == 'base'
    win.confirm = lambda action: True
    panel.approve()
    assert read_state(root)['active'] == item.digest
    assert load(win.store, item.ident).state == 'completed'

    def launch():
        return subprocess.check_output([sys.executable, str(root / 'scripts/launch.py')], text=True).strip()

    assert launch() == 'approved local code'

    second = prepare_improvement(root, root, 'Follow-up', 'MiniMax', change=lambda *args: None)
    assert second.base == item.digest
    assert (Path(second.worktree) / 'main.py').read_text().strip() == 'print("approved local code")'

    rollback(root)
    assert launch() == 'original code'
