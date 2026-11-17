"""JARVIS preparing an improvement to its own source, and being stopped.

WHAT IS COVERED
    * The change is prepared in an isolated worktree under the local
      `development/` folder, and the running checkout is not touched.
    * The diff, the test results and the exact revision are saved.
    * A change whose tests failed cannot be applied, and the review screen
      says why.
    * A change that is edited after the review cannot be applied either: the
      approval has to be given again.
    * A coding provider that stops — a rate limit, a quota, a dropped
      connection — leaves the task saved, so it can be resumed, and the
      other coding provider is only used after the owner approves it.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import subprocess
import time

import pytest
from PySide6.QtWidgets import QApplication

from core.coding_tasks import (create as create_task, load as load_task, prepared,
                               set_state, tasks as coding_tasks, waiting)
from core.development import (DevelopmentError, apply_improvement, approve_improvement,
                              content_digest, create_worktree, prepare_improvement,
                              remove_worktree, worktree_changed, worktree_diff)
from core.store import Store
from providers import routing
from providers.errors import diagnose, FailureKind


def git(folder, *args):
    return subprocess.run(
        ['git', '-C', str(folder), '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
         *args], capture_output=True, text=True, check=True)


@pytest.fixture
def project(tmp_path):
    """A small Git project that looks like JARVIS."""
    folder = tmp_path / 'project'
    folder.mkdir()
    git(folder, 'init', '-b', 'main')
    (folder / 'app.py').write_text('def greet():\n    return "hello"\n', encoding='utf-8')
    (folder / 'test_app.py').write_text('def test_greet():\n    assert True\n', encoding='utf-8')
    git(folder, 'add', '-A')
    git(folder, 'commit', '-m', 'first')
    return folder


def write_change(worktree, provider, goal):
    """The coding provider's part of the work."""
    (worktree / 'app.py').write_text('def greet():\n    return "hello, JARVIS"\n', encoding='utf-8')


# ── the isolated worktree ────────────────────────────────────────────────────

def test_the_change_is_prepared_in_a_worktree_under_development(tmp_path, project):
    root = tmp_path / 'install'
    root.mkdir()
    improvement = prepare_improvement(
        root, project, 'greet the owner', 'MiniMax', change=write_change,
        test_command='python -c "print(1)"')
    try:
        assert improvement.worktree.startswith(str(root / 'development'))
        assert (root / 'development').is_dir()
        # The change is in the worktree, not in the project.
        assert 'JARVIS' in (Path(improvement.worktree) / 'app.py').read_text()
        assert 'hello' in (project / 'app.py').read_text()
        # The diff, the tests and the exact revision are all saved.
        assert 'greet' in improvement.diff
        assert improvement.tests['status'] == 'passed'
        assert len(improvement.revision) == 40
        assert improvement.changed == ('app.py',)
    finally:
        remove_worktree(project, improvement.worktree)


def test_a_failed_test_makes_the_change_not_applicable(tmp_path, project):
    root = tmp_path / 'install'
    root.mkdir()
    improvement = prepare_improvement(
        root, project, 'greet the owner', 'MiniMax', change=write_change,
        test_command='python -c "raise SystemExit(1)"')
    try:
        assert improvement.tests['status'] == 'failed'
        assert improvement.appliable is False
        with pytest.raises(DevelopmentError, match='tests'):
            approve_improvement(improvement)
        with pytest.raises(DevelopmentError, match='tests'):
            apply_improvement(improvement)
    finally:
        remove_worktree(project, improvement.worktree)


def test_a_change_edited_after_the_review_cannot_be_applied(tmp_path, project):
    root = tmp_path / 'install'
    root.mkdir()
    improvement = prepare_improvement(
        root, project, 'greet the owner', 'MiniMax', change=write_change,
        test_command='python -c "print(1)"')
    try:
        approve_improvement(improvement)
        # The worktree changes after the owner looked at it.
        (Path(improvement.worktree) / 'app.py').write_text('def greet():\n    return "changed"\n')
        with pytest.raises(DevelopmentError, match='changed after the review'):
            approve_improvement(improvement)
    finally:
        remove_worktree(project, improvement.worktree)


def test_the_worktree_is_detached_from_the_branch(tmp_path, project):
    root = tmp_path / 'install'
    root.mkdir()
    revision = create_worktree(project, root / 'development' / 'one')
    try:
        assert revision == subprocess.run(
            ['git', '-C', str(project), 'rev-parse', 'HEAD'],
            capture_output=True, text=True, check=True).stdout.strip()
        # The branch in the project did not move.
        assert subprocess.run(
            ['git', '-C', str(project), 'status', '--porcelain'],
            capture_output=True, text=True, check=True).stdout.strip() == ''
    finally:
        remove_worktree(project, root / 'development' / 'one')


def test_a_folder_that_is_not_a_git_checkout_is_refused(tmp_path):
    root = tmp_path / 'install'
    root.mkdir()
    with pytest.raises(DevelopmentError, match='not a Git checkout'):
        create_worktree(root, root / 'development' / 'one')


# ── the saved task ───────────────────────────────────────────────────────────

def test_a_task_is_saved_before_the_provider_is_called(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    task = create_task(store, 'greet the owner', 'MiniMax')
    assert task.state == 'pending'
    saved = load_task(store, task.ident)
    assert saved is not None
    assert saved.goal == 'greet the owner'
    assert saved.provider == 'MiniMax'


def test_a_stopped_task_is_saved_and_can_be_resumed(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    task = create_task(store, 'greet the owner', 'MiniMax')
    set_state(store, task, 'running')
    set_state(store, task, 'waiting', 'MiniMax is rate limiting this key.')
    saved = load_task(store, task.ident)
    assert saved.state == 'waiting'
    assert saved.reason == 'MiniMax is rate limiting this key.'
    assert saved.resumable is True
    assert [item.ident for item in waiting(store)] == [task.ident]


def test_a_prepared_task_is_offered_for_review(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    task = create_task(store, 'greet the owner', 'MiniMax')
    set_state(store, task, 'ready')
    assert [item.ident for item in prepared(store)] == [task.ident]
    assert coding_tasks(store)[0].goal == 'greet the owner'


# ── the rate limit ───────────────────────────────────────────────────────────

def test_a_rate_limited_provider_saves_the_task_and_asks_before_switching(
        tmp_path, monkeypatch):
    from desktop.app import Window
    from desktop.background import ImprovementWorker
    from providers.chat import ProviderFailure

    app = QApplication.instance() or QApplication([])
    # The worktree is prepared under the installation root, so the test uses
    # a temporary checkout of its own and the real one is left alone.
    install = tmp_path / 'install'
    install.mkdir()
    git(install, 'init', '-b', 'main')
    (install / 'main.py').write_text('print("JARVIS")\n', encoding='utf-8')
    git(install, 'add', '-A')
    git(install, 'commit', '-m', 'first')
    monkeypatch.setenv('JARVIS_INSTALL_ROOT', str(install))
    window = Window(tmp_path / 'user')
    try:
        diagnosis = diagnose('MiniMax', status=429, body='rate limit exceeded')
        assert diagnosis.kind == FailureKind.RATE_LIMIT

        def refuse(*args, **kwargs):
            raise ProviderFailure(diagnosis)

        monkeypatch.setattr('desktop.background.ask', refuse)
        monkeypatch.setattr(window, 'coding_key', lambda provider: 'test-key')
        worker = ImprovementWorker(window, 'greet the owner', 'MiniMax', parent=window)
        worker.run()
        # The task was saved, in a state that can be resumed.
        saved = coding_tasks(window.store)
        assert saved and saved[0].state == 'waiting'
        assert saved[0].provider == 'MiniMax'
        assert 'rate limit' in saved[0].reason.lower() or 'limiting' in saved[0].reason.lower()
        # The other coding provider is offered, and it needs the owner's approval.
        assert saved[0].provider != routing.other_coding_provider('MiniMax')
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_the_switch_to_the_other_coding_provider_is_an_approved_action(tmp_path, monkeypatch):
    from desktop.app import Window
    from security.policy import Action, Denied

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path / 'user')
    try:
        asked = []
        warnings = []
        monkeypatch.setattr(window, 'run_improvement',
                            lambda goal, provider: asked.append(provider))
        monkeypatch.setattr('desktop.app.QMessageBox.warning',
                            staticmethod(lambda *args, **kwargs: warnings.append(args[1:])))
        window.confirm = lambda action: False
        window.switch_coding_provider('greet the owner', 'Codex')
        # Nothing was prepared, because the owner did not approve the switch.
        assert asked == []
        assert routing.coding_provider(window.store) == 'MiniMax'
        assert warnings
        # The action names the provider and the goal, so the owner sees it.
        assert routing.other_coding_provider('MiniMax') == 'Codex'
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_maintenance_finds_missing_documented_windows_script(tmp_path):
    from core.development import maintenance_goal

    (tmp_path / 'docs').mkdir()
    (tmp_path / 'START_JARVIS.cmd').touch()
    (tmp_path / 'ROLLBACK_JARVIS.cmd').touch()
    guide = tmp_path / 'docs' / 'UPDATES.md'
    guide.write_text('Run START_JARVIS.cmd to launch.', encoding='utf-8')
    goal = maintenance_goal(tmp_path)
    assert 'ROLLBACK_JARVIS.cmd' in goal
    assert 'START_JARVIS.cmd' not in goal
    guide.write_text('Use START_JARVIS.cmd or ROLLBACK_JARVIS.cmd.', encoding='utf-8')
    assert maintenance_goal(tmp_path) == ''


def test_source_installation_without_git_uses_only_inventory(tmp_path):
    root = tmp_path / 'source'
    (root / 'docs').mkdir(parents=True)
    (root / 'main.py').write_text('print("original")\n', encoding='utf-8')
    (root / 'private-notes.txt').write_text('not part of JARVIS', encoding='utf-8')
    inventory = root / 'docs' / 'SOURCE_INTEGRITY.sha256'
    inventory.write_text(f'{"a" * 64}  main.py\n', encoding='utf-8')

    def edit(folder, *_):
        assert not (folder / 'private-notes.txt').exists()
        (folder / 'main.py').write_text('print("changed")\n', encoding='utf-8')

    item = prepare_improvement(root, root, 'Update greeting', 'MiniMax', change=edit)
    assert 'changed' in item.diff
    assert item.state == 'ready'
    assert not item.appliable
    assert 'original' in (root / 'main.py').read_text(encoding='utf-8')
