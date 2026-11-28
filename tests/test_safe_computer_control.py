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



def test_automation_route_closes_settings_and_opens_the_existing_chat_panel(tmp_path):
    from PySide6.QtWidgets import QPushButton
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        window.open_section('Settings & Safety')
        window.show_settings_panel('Approvals')
        settings = window.settings_scroller
        assert not any(button.text() == 'PC Control' for button in settings.findChildren(QPushButton))
        window.open_section('PC Control')
        assert not window.prime_shell.settings_dialog.isVisible()
        assert window.pages.currentWidget() is window.prime_chat
        assert window.prime_chat.task_area.currentIndex() == window.prime_chat.task_panels['PC Control']
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_open_file_and_folder_use_distinct_pickers_and_require_approval(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QPushButton
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    file_path = tmp_path / 'example.txt'
    file_path.write_text('example', encoding='utf-8')
    opened, approvals = [], []
    monkeypatch.setattr('desktop.app.QFileDialog.getOpenFileName', lambda *_: (str(file_path), ''))
    monkeypatch.setattr('desktop.app.QFileDialog.getExistingDirectory', lambda *_: str(tmp_path))
    monkeypatch.setattr('desktop.app.QMessageBox.warning', lambda *_: None)
    monkeypatch.setattr('desktop.app.open_path', lambda path: opened.append(path) or 'Opened')
    window.confirm = lambda action: approvals.append(action) or action.target == str(tmp_path)
    try:
        window.open_section('PC Control')
        panel = window.prime_chat.task_area.currentWidget()
        buttons = {button.text(): button for button in panel.findChildren(QPushButton)}
        buttons['Open file…'].click()
        buttons['Open folder…'].click()
        assert approvals == [Action('open_path', str(file_path)), Action('open_path', str(tmp_path))]
        assert opened == [str(tmp_path)]
        assert {row['status'] for row in window.store.tasks()} == {'denied', 'completed'}
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_camera_preview_stops_before_device_access_if_owner_declines():
    from types import SimpleNamespace
    from desktop.camera_reader import open_camera_reader

    requested = []
    window = SimpleNamespace(policy=Policy(),
                             confirm=lambda action: requested.append(action) or False)
    assert open_camera_reader(window) is None
    assert requested == [Action('Start camera preview', 'Selected local camera')]


def test_verified_scroll_checks_actual_position_and_never_replays(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    import sys
    from automation import app_control

    scroll_amount = SimpleNamespace(NoAmount=0, SmallIncrement=1, SmallDecrement=-1)
    monkeypatch.setitem(sys.modules, 'System.Windows.Automation', SimpleNamespace(
        ScrollAmount=scroll_amount, ScrollPattern=SimpleNamespace(Pattern=1)))
    position = SimpleNamespace(VerticallyScrollable=True, VerticalScrollPercent=25.0)
    calls = []
    can_move = True

    def scroll(horizontal, vertical):
        calls.append((horizontal, vertical))
        if can_move:
            position.VerticalScrollPercent = 40.0

    pattern = SimpleNamespace(Current=position, Scroll=scroll)
    control = SimpleNamespace(GetCurrentPattern=lambda _: pattern)

    @contextmanager
    def selected(*_args):
        yield control, 'Project panel', lambda: None

    monkeypatch.setattr(app_control, '_selected_control', selected)
    assert 'from 25% to 40%' in app_control.scroll_control(7, 'App', 'Project panel', direction='down')
    assert calls == [(0, 1)]
    can_move = False
    ticks = iter((0.0, 1.0))
    monkeypatch.setattr(app_control, 'time', SimpleNamespace(monotonic=lambda: next(ticks)))
    with pytest.raises(app_control.InputRefused, match='did not verify'):
        app_control.scroll_control(7, 'App', 'Project panel', direction='down')
    assert calls == [(0, 1), (0, 1)]


def test_pointed_selection_requires_original_control_and_readback(monkeypatch):
    import sys
    from contextlib import contextmanager
    from types import SimpleNamespace
    from automation import app_control

    monkeypatch.setitem(sys.modules, 'System.Windows.Automation', SimpleNamespace(
        SelectionItemPattern=SimpleNamespace(Pattern=1)))
    monkeypatch.setattr(app_control.win_controls, 'foreground_process', lambda: 7)
    state = SimpleNamespace(IsSelected=False)
    calls = []

    def control(runtime_id):
        pattern = SimpleNamespace(Current=state, Select=lambda: calls.append(runtime_id))
        return SimpleNamespace(GetRuntimeId=lambda: runtime_id, GetCurrentPattern=lambda _: pattern)

    controls = [control((2, 8)), control((2, 9))]
    monkeypatch.setattr(app_control, '_usable', lambda *_: ('Clip', '', 'ListItem'))

    @contextmanager
    def foreground(*_):
        yield controls, lambda: None

    monkeypatch.setattr(app_control, '_foreground_app', foreground)
    with pytest.raises(app_control.InputRefused, match='did not verify'):
        app_control.select_control(7, 'Editor', 'Clip', runtime_id=(2, 9))
    assert calls == [(2, 9)]
    state.IsSelected = True
    assert "'Clip' is selected" in app_control.select_control(7, 'Editor', 'Clip', runtime_id=(2, 9))
    controls.pop()
    with pytest.raises(app_control.InputRefused, match='missing or ambiguous'):
        app_control.select_control(7, 'Editor', 'Clip', runtime_id=(2, 9))
    assert calls == [(2, 9), (2, 9)]


def test_pointer_hit_must_be_an_accessible_control_in_the_selected_window(monkeypatch):
    import sys
    from contextlib import contextmanager
    from types import SimpleNamespace
    from automation import app_control

    monkeypatch.setitem(sys.modules, 'System.Windows', SimpleNamespace(Point=lambda x, y: (x, y)))
    monkeypatch.setattr(app_control.ctypes, 'windll', SimpleNamespace(
        user32=SimpleNamespace(GetCursorPos=lambda _: True)), raising=False)
    control = SimpleNamespace(GetRuntimeId=lambda: (4, 1))
    hit = control
    monkeypatch.setattr(app_control.uia, 'load_client', lambda: SimpleNamespace(FromPoint=lambda _: hit))
    properties = ('Clip', '', 'ListItem')
    monkeypatch.setattr(app_control, '_usable', lambda *_: properties)

    @contextmanager
    def foreground(*_):
        yield [control], lambda: None

    monkeypatch.setattr(app_control, '_foreground_app', foreground)
    assert app_control.pointed_control(7, 'Editor', selecting=True) == ('Clip', '', (4, 1))
    hit = SimpleNamespace(GetRuntimeId=lambda: (4, 2))
    with pytest.raises(app_control.InputRefused, match='Point at a named control'):
        app_control.pointed_control(7, 'Editor', selecting=True)
    hit = control
    properties = None
    with pytest.raises(app_control.InputRefused, match='Point at a named control'):
        app_control.pointed_control(7, 'Editor', selecting=True)


def test_drag_releases_mouse_after_partial_delivery_and_checks_path(monkeypatch):
    from unittest.mock import Mock
    from types import SimpleNamespace
    from automation import input as desktop_input
    from automation import win_controls

    metrics = {76: -100, 77: 0, 78: 200, 79: 100}
    user = SimpleNamespace(
        GetSystemMetrics=metrics.__getitem__, GetAsyncKeyState=lambda _: 0,
        SetCursorPos=lambda *_: True, GetCursorPos=lambda ref: True,
        WindowFromPoint=Mock(return_value=11), GetAncestor=Mock(return_value=10),
    )

    def cursor(ref):
        ref._obj.x, ref._obj.y = -25, 30
        return True

    user.GetCursorPos = cursor
    monkeypatch.setattr(desktop_input.ctypes, 'windll', SimpleNamespace(user32=user), raising=False)
    monkeypatch.setattr(desktop_input, '_windows_only', lambda: None)
    monkeypatch.setattr(win_controls, 'foreground_window', lambda: 10)
    sent = Mock(side_effect=[2, 1])
    monkeypatch.setattr(desktop_input, 'send_input', sent)
    target = desktop_input.InputTarget(7, 'Editor')
    with pytest.raises(desktop_input.InputRefused, match='complete drag'):
        desktop_input.drag_between((-25, 30), (25, 30), target, foreground=lambda: 7)
    drag, cleanup = [call.args[0] for call in sent.call_args_list]
    assert len(drag) == 10
    assert drag[0].data.mi.dwFlags == 0x0002
    assert drag[-1].data.mi.dwFlags == cleanup[0].data.mi.dwFlags == 0x0004
    assert drag[-2].data.mi.dx == 40960
    sent.reset_mock()
    user.GetAncestor.return_value = 12
    with pytest.raises(desktop_input.InputRefused, match='crosses another window'):
        desktop_input.drag_between((-25, 30), (25, 30), target, foreground=lambda: 7)
    sent.assert_not_called()


@pytest.mark.parametrize('moves', [True, False])
def test_drag_requires_original_item_inside_destination(monkeypatch, moves):
    import sys
    from contextlib import contextmanager
    from types import SimpleNamespace
    from automation import app_control

    class Items(list):
        @property
        def Count(self):
            return len(self)

    monkeypatch.setitem(sys.modules, 'System.Windows.Automation', SimpleNamespace(
        TreeScope=SimpleNamespace(Descendants=1), Condition=SimpleNamespace(TrueCondition=1)))
    source = SimpleNamespace(GetRuntimeId=lambda: [1, 2],
                             GetClickablePoint=lambda: SimpleNamespace(X=15, Y=15))
    duplicate = SimpleNamespace(GetRuntimeId=lambda: [1, 3])
    placed = Items()
    container = SimpleNamespace(FindAll=lambda *_: placed, GetRuntimeId=lambda: [1, 4],
                                GetClickablePoint=lambda: SimpleNamespace(X=55, Y=55))
    dispatches = []

    @contextmanager
    def selected(pid, title, name, _, kinds, checkpoint, **options):
        yield (source if name == 'Clip A' else container), name, checkpoint

    def dispatch(start, end, target, *, foreground):
        assert start == (15, 15) and end == (55, 55)
        assert foreground() == target.process_id
        dispatches.append(True)
        placed.append(source if moves else duplicate)

    monkeypatch.setattr(app_control, '_selected_control', selected)
    monkeypatch.setattr(app_control, '_point_hits', lambda *_: True)
    monkeypatch.setattr(app_control.desktop_input, 'drag_between', dispatch)
    monkeypatch.setattr(app_control, 'time', SimpleNamespace(monotonic=iter((0, 2)).__next__))
    if moves:
        assert "moved into 'Bins'" in app_control.drag_control(7, 'Editor', 'Clip A', destination='Bins')
    else:
        with pytest.raises(app_control.InputRefused, match='could not verify'):
            app_control.drag_control(7, 'Editor', 'Clip A', destination='Bins')
    assert dispatches == [True]
