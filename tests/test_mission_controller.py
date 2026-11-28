"""The mission console wired into the running desktop.

WHAT IS COVERED
    * A mission started from the console reaches the provider the owner
      chose and the answer comes back to the console.
    * A tool the model asks for really runs, and its real result is
      what the mission is built on.
    * A tool that changes something asks the owner through the real
      approval dialog path, and the owner's answer decides.
    * A refused tool does not run, and the mission says it was refused.
    * Cancelling a mission stops it.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from threading import Event

import json
import time

import httpx
import pytest
from PySide6.QtWidgets import QApplication

from desktop.app import Window
from providers.router import ProviderRouter


class TestVault:
    """A key that is not a key, so no request can reach a real service."""

    def get(self, provider):
        return 'test-key-not-real'


def answer_stream(text):
    """A provider answer that carries one JSON envelope."""
    return ('data: ' + json.dumps({'choices': [{'delta': {'content': text}}]})
            + '\n\ndata: [DONE]\n\n')


def tool_call(name, arguments=None):
    return json.dumps({'action': 'tool', 'tool': name, 'arguments': arguments or {},
                       'thought': 'One step at a time.'})


def final(text):
    return json.dumps({'action': 'answer', 'answer': text, 'thought': 'That is it.'})


def wait_for(predicate, timeout=15):
    """Let the interface breathe until the predicate is true."""
    deadline = time.monotonic() + timeout
    app = QApplication.instance()
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


def answer_proposal(window, *, approve=True, edit=None):
    """Answer the proposed action that is waiting in Automation.

    A proposed action is a card with Run, Edit and Dismiss. The owner
    answers it there, whichever engine proposed it.
    """
    deadline = time.monotonic() + 15
    app = QApplication.instance()
    while time.monotonic() < deadline:
        app.processEvents()
        cards = window.automation_panel.cards()
        if cards:
            card = cards[0]
            if edit:
                card.editor.setVisible(True)
                for name, value in edit.items():
                    card.fields[name].setText(value)
            if approve:
                card.run_button.click()
            else:
                card.dismiss_button.click()
            return card.action
        time.sleep(0.005)
    return None


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    win.vault = TestVault()
    yield win
    win.close()
    win.deleteLater()
    app.processEvents()


def connect(window, bodies):
    """Give the window a provider that answers with the given bodies."""
    state = {'index': 0}

    def handler(request):
        body = bodies[min(state['index'], len(bodies) - 1)]
        state['index'] += 1
        return httpx.Response(200, text=answer_stream(body))

    window.router = ProviderRouter(transport=httpx.MockTransport(handler))


def test_a_mission_answers_and_the_console_shows_it(window):
    connect(window, [final('The launch is on Friday.')])
    window.mission_controller.start('When is the launch?')
    assert wait_for(lambda: window.mission_panel.status.text() == 'COMPLETE')
    assert window.mission_panel.evidence_column.answer.text() == 'The launch is on Friday.'
    kinds = [entry['kind'] for entry in window.mission_panel.timeline.entries()]
    assert kinds[0] == 'goal'
    assert kinds[-1] == 'answer'


def test_a_tool_the_model_asks_for_really_runs(window):
    connect(window, [tool_call('evaluate_expression', {'expression': '6 * 7'}),
                     final('It is 42.')])
    window.mission_controller.start('What is six times seven?')
    assert wait_for(lambda: window.mission_panel.status.text() == 'COMPLETE')
    evidence = window.mission_panel.evidence_column.count.text()
    assert 'tool result' in evidence
    assert window.mission_panel.evidence_column.answer.text() == 'It is 42.'


def test_a_tool_that_changes_something_asks_the_owner(window):
    connect(window, [tool_call('memory_remember',
                               {'title': 'Launch', 'body': 'On Friday.', 'tags': []}),
                     final('Saved.')])
    window.mission_controller.start('Remember that the launch is on Friday.')
    proposed = answer_proposal(window)
    assert proposed is not None
    assert proposed.kind == 'mission_tool'
    assert 'memory_remember' in proposed.target
    assert wait_for(lambda: window.mission_panel.status.text() == 'COMPLETE')
    assert 'tool result' in window.mission_panel.evidence_column.count.text()


def test_the_owner_can_edit_a_proposed_action_before_it_runs(window):
    connect(window, [tool_call('memory_remember',
                               {'title': 'Launch', 'body': 'On Friday.', 'tags': []}),
                     final('Saved.')])
    window.mission_controller.start('Remember that the launch is on Friday.')
    proposed = answer_proposal(window, edit={'body': 'On Monday.'})
    assert proposed is not None
    assert 'body' in proposed.editable
    assert wait_for(lambda: window.mission_panel.status.text() == 'COMPLETE')
    titles = [row.title for row in window.memory_service.all()]
    assert 'On Monday.' in [row.body for row in window.memory_service.all()]


def test_a_refused_tool_does_not_run(window):
    connect(window, [tool_call('memory_remember',
                               {'title': 'Launch', 'body': 'On Friday.', 'tags': []}),
                     final('Saved.')])
    window.mission_controller.start('Remember that the launch is on Friday.')
    proposed = answer_proposal(window, approve=False)
    assert proposed is not None
    assert wait_for(lambda: window.mission_panel.status.text() == 'FAILED')
    assert window.mission_panel.evidence_column.count.text() == 'no tool result recorded'
    labels = ' '.join(entry['label'] for entry in window.mission_panel.timeline.entries())
    assert 'did not allow' in labels


def test_a_second_mission_does_not_disturb_the_first(window):
    entered = Event()
    release = Event()

    def slow(request):
        entered.set()
        assert release.wait(30)
        return httpx.Response(200, text=answer_stream(tool_call(
            'evaluate_expression', {'expression': '1 + 1'})))

    window.router = ProviderRouter(transport=httpx.MockTransport(slow))
    window.mission_controller.start('Add one and one.')
    assert wait_for(entered.is_set)
    window.mission_controller.start('And another thing.')
    labels = ' '.join(entry['label'] for entry in window.mission_panel.timeline.entries())
    assert 'A mission is already running' in labels
    # The running mission keeps its own state: the console does not say
    # that a mission failed while one of them is still working.
    assert window.mission_panel.status.text() == 'WORKING'
    window.mission_controller.cancel()
    release.set()
    assert wait_for(lambda: window.mission_panel.status.text() in ('CANCELLED', 'FAILED'))


def test_a_mission_can_be_cancelled(window):
    def slow(request):
        # A provider that takes a moment, so the cancellation lands in
        # the middle of the mission instead of after it.
        time.sleep(0.2)
        return httpx.Response(200, text=answer_stream(tool_call(
            'evaluate_expression', {'expression': '1 + 1'})))

    window.router = ProviderRouter(transport=httpx.MockTransport(slow))
    window.mission_controller.start('Add one and one.')
    assert wait_for(lambda: window.mission_panel.timeline.entries())
    window.mission_controller.cancel()
    assert wait_for(lambda: window.mission_panel.status.text() in
                    ('CANCELLED', 'FAILED', 'COMPLETE'))
    assert window.mission_panel.status.text() != 'COMPLETE'


def test_review_interrupted_mission_runs_only_remaining_goal(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    store = window.store
    old = store.task('mission', 'original private goal')
    receipt = 'Check before retrying: step 3, click_app_control'
    store.finish(old, 'interrupted', receipt)
    controller = window.mission_controller
    controller.refresh_recovery()
    button = window.mission_panel.recovery_button
    assert not button.isHidden()
    responses = iter([('ignored', False), ('  inspect the output  ', True)])

    def review(parent, title, prompt):
        assert receipt in prompt
        return next(responses)

    monkeypatch.setattr(QInputDialog, 'getText', review)
    button.click()
    assert store.interrupted_mission()['id'] == old
    connect(window, [final('Reviewed.')])
    button.click()
    assert wait_for(lambda: window.mission_panel.status.text() == 'COMPLETE')
    assert window.mission_panel.title.text() == 'inspect the output'
    assert not window.automation_panel.cards()
    assert button.isHidden()
    assert next(row for row in store.tasks() if row['id'] == old)['status'] == 'continued'
    with pytest.raises(ValueError):
        store.continue_mission(old)
