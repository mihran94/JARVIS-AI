"""Multi-step requests use the existing one-use approval and focus boundaries."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
import pytest
from PySide6.QtWidgets import QApplication
from desktop.app import Window
from desktop.conversation_plan import parse_plan


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    w = Window(tmp_path)
    monkeypatch.setattr(w, 'get_key', lambda *_: pytest.fail('No AI call for explicit local plans'))
    yield w
    w.close()
    app.processEvents()


def send(w, text):
    w.prompt.setPlainText(text)
    w.send()


def test_natural_steps_and_literal_text_are_separate():
    plan = parse_plan('Jarvis, open Calculator then open Notepad and type: தமிழ் then KEEP This!')
    assert [step.app for step in plan] == ['Calculator', 'Notepad']
    assert plan[-1].typing.text == 'தமிழ் then KEEP This!'
    assert parse_plan('Jarvis, notepad open pannu apram calculator open pannu')[1].app == 'Calculator'
    assert parse_plan('ஜார்விஸ், notepad திற பிறகு calculator திற')[1].app == 'Calculator'


@pytest.mark.parametrize('text', [
    'How do I open Notepad then open Calculator?',
    'Do not open Notepad then open Calculator',
    '"open Notepad then open Calculator"',
    'Jarvis, should I open Notepad then open Calculator?',
])
def test_questions_and_quotes_stay_conversation(text):
    assert parse_plan(text) is None


@pytest.mark.parametrize('text', [
    '/do', '/do open powershell',
    'open Notepad then delete files',
    '/do open Notepad then open Calculator; shutdown',
    '/do ' + ' then '.join(['open Notepad'] * 7),
])
def test_invalid_whole_plan_is_rejected(text):
    with pytest.raises(ValueError):
        parse_plan(text)


def test_every_step_waits_and_decline_cancels_the_rest(window, monkeypatch):
    launches = []
    monkeypatch.setattr('desktop.app.launch_app', lambda name: launches.append(name) or 'Launch request accepted')
    send(window, 'Jarvis, open Notepad then open Calculator then open Notepad')
    assert launches == []
    assert window.chat_reactor.height() == 88
    assert '1. Open Notepad' in window.transcript.toPlainText()
    window.finish_chat_launch(True)
    assert launches == ['Notepad']
    assert window.chat_launch[0] == 'Calculator'
    window.finish_chat_launch(False)
    assert launches == ['Notepad']
    assert window.conversation_plan.active is None
    assert window.store.tasks()[-1]['status'] == 'cancelled'
    assert window.chat_reactor.height() == 170


def test_typing_waits_for_approval_and_foreground(window, monkeypatch):
    launches, typed = [], []
    foreground = [False]
    monkeypatch.setattr('desktop.app.launch_app', lambda name: launches.append(name) or 'Launch request accepted')
    monkeypatch.setattr('desktop.app.target_is_foreground', lambda _: foreground[0])
    monkeypatch.setattr('desktop.app.type_into_target', lambda app, text: typed.append(text) or 'Input dispatched; saved content not verified')
    send(window, '/do open Calculator then open Notepad and type: வணக்கம் then literal text')
    window.finish_chat_launch(True)
    assert launches == ['Calculator']
    assert typed == []
    window.finish_chat_launch(True)
    assert launches == ['Calculator', 'Notepad']
    assert window.conversation_plan.active is not None
    window.complete_desktop_task()
    assert typed == []
    foreground[0] = True
    window.complete_desktop_task()
    assert typed == ['வணக்கம் then literal text']
    assert window.conversation_plan.active is None
    assert 'content and saved files are not verified' in window.transcript.toPlainText()


def test_failed_launch_stops_remaining_steps(window, monkeypatch):
    def fail(name):
        raise RuntimeError('App unavailable')
    monkeypatch.setattr('desktop.app.launch_app', fail)
    send(window, '/do open Notepad then open Calculator')
    window.finish_chat_launch(True)
    assert window.chat_launch is None
    assert window.conversation_plan.active is None
    assert 'Plan failed' in window.transcript.toPlainText()


def test_emergency_stop_never_replays_after_resume(window, monkeypatch):
    launches = []
    monkeypatch.setattr('desktop.app.launch_app', lambda name: launches.append(name))
    send(window, '/do open Notepad then open Calculator')
    window.stop()
    window.resume()
    window.finish_chat_launch(True)
    assert launches == []
    assert window.conversation_plan.active is None


def test_cancel_pending_typing_prevents_late_timer(window, monkeypatch):
    typed = []
    monkeypatch.setattr('desktop.app.launch_app', lambda _: 'Launch requested')
    monkeypatch.setattr('desktop.app.target_is_foreground', lambda _: True)
    monkeypatch.setattr('desktop.app.type_into_target', lambda *args: typed.append(args))
    send(window, '/do open Notepad and type: secret note')
    window.finish_chat_launch(True)
    send(window, '/cancel')
    window.complete_desktop_task()
    assert typed == []
    assert window.desktop_pending is None
    assert window.conversation_plan.active is None


def test_foreground_timeout_is_a_failed_plan(window, monkeypatch):
    monkeypatch.setattr('desktop.app.launch_app', lambda _: 'Launch requested')
    send(window, '/do open Notepad and type: note')
    window.finish_chat_launch(True)
    window.desktop_pending['deadline'] = time.monotonic() - 1
    window.complete_desktop_task()
    assert window.conversation_plan.active is None
    assert 'Plan failed' in window.transcript.toPlainText()


def test_new_chat_cancels_plan_in_original_session(window, monkeypatch):
    launches = []
    monkeypatch.setattr('desktop.app.launch_app', lambda name: launches.append(name))
    send(window, '/do open Notepad then open Calculator')
    original = window.session
    window.new_chat()
    window.finish_chat_launch(True)
    assert launches == []
    assert window.session != original
    assert not window.store.messages(window.session)
    assert any('Plan cancelled' in m['content'] for m in window.store.messages(original))


def test_bad_later_step_does_not_prepare_first(window):
    send(window, '/do open Notepad then delete files')
    assert window.chat_launch is None
    assert window.conversation_plan.active is None
    assert 'Nothing was started' in window.transcript.toPlainText()


def test_second_request_does_not_replace_approval(window):
    send(window, '/do open Notepad then open Calculator')
    pending = window.chat_launch
    send(window, 'open Calculator')
    assert window.chat_launch is pending
    assert window.prompt.toPlainText() == 'open Calculator'


def test_disabled_plugin_fails_without_launch(window):
    window.store.set('plugin:Google Flow', False)
    send(window, '/do open Google Flow then open Notepad')
    assert window.chat_launch is None
    assert window.conversation_plan.active is None
    assert 'disabled' in window.transcript.toPlainText()


def test_successful_launch_plan_keeps_actual_results(window, monkeypatch):
    launches = []
    monkeypatch.setattr('desktop.app.launch_app', lambda name: launches.append(name) or f'{name}: process launch accepted')
    send(window, 'Jarvis, open Notepad and then open Calculator')
    window.finish_chat_launch(True)
    assert launches == ['Notepad']
    window.finish_chat_launch(True)
    assert launches == ['Notepad', 'Calculator']
    plan = next(t for t in window.store.tasks() if t['kind'] == 'conversation_plan')
    assert plan['status'] == 'completed'
    assert 'requests dispatched' in plan['detail']
    assert window.conversation_plan.active is None


def test_stop_inside_action_prevents_next_step(window, monkeypatch):
    launches = []
    def launch(name):
        launches.append(name)
        window.stop()
        return 'Launch accepted'
    monkeypatch.setattr('desktop.app.launch_app', launch)
    send(window, '/do open Notepad then open Calculator')
    window.finish_chat_launch(True)
    window.resume()
    assert launches == ['Notepad']
    assert window.chat_launch is None
    assert window.conversation_plan.active is None


def test_closed_window_leaves_no_replayable_plan(window):
    send(window, '/do open Notepad then open Calculator')
    window.close()
    assert window.conversation_plan.active is None
    assert window.chat_launch is None
    plan = next(t for t in window.store.tasks() if t['kind'] == 'conversation_plan')
    assert plan['status'] == 'cancelled'
