"""Safe computer control: what is allowed, what is refused, what is left alone.

WHAT IS COVERED
    * The approval boundary is visible. The owner can see what was
      allowed, what was refused, and what an emergency stop threw away.
    * An emergency stop really does invalidate a pending approval, and
      the record says "stopped", not "refused": the owner never said no.
    * Tidy a folder means: only the top level of the one folder the
      owner chose, never overwriting, never moving a secret or a hidden
      file, and only what the plan said.
    * Nothing moves before the owner has seen the plan.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from automation.organise import (
    OrganiseError, category_of, organise, plan_organise, plan_text, result_text,
)
from security.policy import Action, Denied, Policy, Stopped


# ── the approval boundary, made visible ─────────────────────────────────────

def test_the_boundary_records_what_it_allowed():
    policy = Policy()
    action = Action('launch_app', 'Notepad')
    token = policy.approve(action, lambda _a: True)
    policy.execute(action, token, lambda: 'opened')
    counts = policy.decision_counts()
    assert counts.get('allowed') == 1
    assert 'allowed' in policy.summary()


def test_a_refusal_is_recorded_as_a_refusal():
    policy = Policy()
    with pytest.raises(Denied):
        policy.approve(Action('launch_app', 'Notepad'), lambda _a: False)
    assert policy.decision_counts().get('refused') == 1
    assert policy.decisions()[-1].outcome == 'refused'


def test_an_emergency_stop_throws_the_pending_approval_away():
    policy = Policy()
    action = Action('launch_app', 'Notepad')
    token = policy.approve(action, lambda _a: True)
    policy.stop()
    # The approval is dead, and it is dead for good.
    with pytest.raises(Denied):
        policy.execute(action, token, lambda: 'opened')
    assert policy.invalidated == 1
    outcomes = {decision.outcome for decision in policy.decisions()}
    assert 'stopped' in outcomes


def test_a_stopped_approval_is_not_recorded_as_a_refusal():
    """The owner never said no, so it must not read as a refusal."""
    policy = Policy()
    action = Action('launch_app', 'Notepad')
    token = policy.approve(action, lambda _a: True)
    policy.stop()
    with pytest.raises(Denied):
        policy.execute(action, token, lambda: 'opened')
    assert policy.decision_counts().get('refused') in (None, 0)
    # The stop is recorded when it happens, and again when the dead
    # approval is finally presented. Both say "stopped".
    assert policy.decision_counts().get('stopped', 0) >= 1


def test_resume_does_not_bring_the_old_approval_back():
    policy = Policy()
    action = Action('launch_app', 'Notepad')
    token = policy.approve(action, lambda _a: True)
    policy.stop()
    policy.resume()
    with pytest.raises(Denied):
        policy.execute(action, token, lambda: 'opened')


def test_the_record_is_bounded():
    policy = Policy()
    for index in range(400):
        action = Action('launch_app', f'app{index}')
        token = policy.approve(action, lambda _a: True)
        policy.execute(action, token, lambda: 'ok')
    assert len(policy.decisions()) <= 200


# ── tidying a folder ───────────────────────────────────────────────────────

def make_folder(tmp_path):
    (tmp_path / 'notes.pdf').write_text('a document', encoding='utf-8')
    (tmp_path / 'photo.png').write_bytes(b'\x89PNG\r\n\x1a\n')
    (tmp_path / 'code.py').write_text('X = 1\n', encoding='utf-8')
    (tmp_path / 'unknown.xyz').write_text('what is this', encoding='utf-8')
    (tmp_path / '.hidden').write_text('hidden', encoding='utf-8')
    return tmp_path


def test_the_plan_says_what_would_move_and_where(tmp_path):
    plan = plan_organise(make_folder(tmp_path))
    moves = dict(plan.moves)
    assert 'notes.pdf' in moves
    # The folder is named, not the whole path: the separator is the one
    # of the machine the test runs on.
    assert Path(moves['notes.pdf']).parent.name == 'documents'
    assert Path(moves['photo.png']).parent.name == 'images'
    assert Path(moves['code.py']).parent.name == 'code'
    # A file of no known kind is left where it is.
    assert 'unknown.xyz' in plan.left_alone
    assert '3 file(s) would move' in plan_text(plan)


def test_a_hidden_file_is_never_moved(tmp_path):
    plan = plan_organise(make_folder(tmp_path))
    assert '.hidden' in plan.left_alone
    assert not any(name == '.hidden' for name, _ in plan.moves)


def test_a_file_that_looks_like_a_secret_is_never_moved(tmp_path):
    (tmp_path / 'secrets.json').write_text('{"key": "x"}', encoding='utf-8')
    plan = plan_organise(tmp_path)
    assert 'secrets.json' in plan.left_alone
    assert not any(name == 'secrets.json' for name, _ in plan.moves)


def test_nothing_is_moved_before_the_plan_is_carried_out(tmp_path):
    make_folder(tmp_path)
    plan_organise(tmp_path)
    assert (tmp_path / 'notes.pdf').exists()
    assert not (tmp_path / 'documents').exists()


def test_only_the_top_level_of_the_chosen_folder_is_used(tmp_path):
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'deep.pdf').write_text('deep', encoding='utf-8')
    plan = plan_organise(tmp_path)
    assert not any(name == 'deep.pdf' for name, _ in plan.moves)


def test_a_file_is_never_overwritten(tmp_path):
    (tmp_path / 'notes.pdf').write_text('a document', encoding='utf-8')
    (tmp_path / 'documents').mkdir()
    (tmp_path / 'documents' / 'notes.pdf').write_text('already here', encoding='utf-8')
    plan = plan_organise(tmp_path)
    assert 'notes.pdf' in plan.left_alone
    result = organise(plan)
    assert (tmp_path / 'documents' / 'notes.pdf').read_text(encoding='utf-8') == 'already here'


def test_the_plan_is_carried_out_and_the_result_is_reported(tmp_path):
    make_folder(tmp_path)
    plan = plan_organise(tmp_path)
    result = organise(plan)
    assert (tmp_path / 'documents' / 'notes.pdf').exists()
    assert (tmp_path / 'images' / 'photo.png').exists()
    assert (tmp_path / 'code' / 'code.py').exists()
    # The file of no known kind has not moved.
    assert (tmp_path / 'unknown.xyz').exists()
    assert '3 file(s) moved' in result_text(result)


def test_a_folder_that_is_not_there_is_refused(tmp_path):
    with pytest.raises(OrganiseError):
        plan_organise(tmp_path / 'missing')


def test_the_number_of_files_is_bounded(tmp_path):
    for index in range(600):
        (tmp_path / f'file{index}.pdf').write_text('x', encoding='utf-8')
    plan = plan_organise(tmp_path)
    assert plan.move_count <= 500
    assert plan.truncated is True


def test_a_file_of_a_known_kind_is_recognised():
    from pathlib import Path
    assert category_of(Path('a.pdf')) == 'documents'
    assert category_of(Path('a.png')) == 'images'
    assert category_of(Path('a.zip')) == 'archives'
    assert category_of(Path('a.py')) == 'code'
    assert category_of(Path('a.mp4')) == 'media'
    assert category_of(Path('a.qqq')) == ''


# ── in the application ──────────────────────────────────────────────────────

def test_the_page_shows_the_owner_what_the_boundary_has_done(tmp_path):
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        action = Action('launch_app', 'Notepad')
        token = window.policy.approve(action, lambda _a: True)
        window.policy.execute(action, token, lambda: 'opened')
        window.refresh_safety_report()
        assert 'allowed' in window.safety_report.text()
        assert 'launch_app' in window.safety_details.toPlainText()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
