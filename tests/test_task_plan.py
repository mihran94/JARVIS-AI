"""The state of a multi-step job, and the rule for retrying a step.

WHAT IS COVERED
    * A step is in exactly one state, and the states are the ones the
      owner is shown: pending, waiting for approval, running, verified,
      failed and cancelled.
    * A step that was verified cannot be tried again. The consequence it
      produced already happened.
    * A failed step can be tried again, and the steps before it keep
      their state, so the work that succeeded does not happen again.
    * The summary counts the steps and never invents a percentage.
    * The state of a plan survives the window closing, so the owner comes
      back to a plan they can still act on.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from desktop.app import Window
from desktop.task_plan import StepState, TaskPlan


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    w = Window(tmp_path)
    w.show()
    monkeypatch.setattr(w, 'get_key', lambda *_: pytest.fail('No AI call for a local plan'))
    yield w
    w.close()
    w.deleteLater()
    app.processEvents()


def send(window, text):
    window.prompt.setPlainText(text)
    window.send()


def plan_task(window):
    """The task of the plan, not another task in the same history."""
    for task in window.store.tasks():
        if task['kind'] == 'conversation_plan':
            return task
    return None


# ── the model ───────────────────────────────────────────────────────────────

def test_a_new_plan_has_its_steps_pending():
    plan = TaskPlan.build(['Open Notepad', 'Open Calculator'])
    assert [step.state for step in plan.steps] == [StepState.PENDING, StepState.PENDING]
    assert plan.next_pending().label == 'Open Notepad'


def test_a_step_moves_through_the_states():
    plan = TaskPlan.build(['Open Notepad'])
    step = plan.steps[0]
    plan.wait(step.ident)
    assert step.state == StepState.WAITING
    plan.run(step.ident)
    assert step.state == StepState.RUNNING
    assert step.attempts == 1
    plan.verify(step.ident, 'the window came forward')
    assert step.state == StepState.VERIFIED
    assert step.detail == 'the window came forward'


def test_a_verified_step_cannot_be_changed_again():
    plan = TaskPlan.build(['Open Notepad'])
    step = plan.steps[0]
    plan.verify(step.ident)
    with pytest.raises(ValueError):
        plan.run(step.ident)


def test_a_step_that_failed_can_be_tried_again():
    plan = TaskPlan.build(['Open Notepad'])
    step = plan.steps[0]
    plan.run(step.ident)
    plan.fail(step.ident, 'the window did not come forward')
    assert plan.can_retry(step.ident) is True
    plan.retry(step.ident)
    assert step.state == StepState.PENDING
    assert step.attempts == 2


def test_a_verified_step_is_never_run_again():
    """The whole point of the retry rule."""
    plan = TaskPlan.build(['Open Calculator', 'Open Notepad', 'Type the note'])
    first, second, third = plan.steps
    plan.verify(first.ident, 'opened')
    plan.run(second.ident)
    plan.fail(second.ident, 'the window did not come forward')
    plan.retry(second.ident)
    assert first.state == StepState.VERIFIED
    assert first.attempts == 0
    assert second.state == StepState.PENDING
    assert third.state == StepState.PENDING


def test_the_steps_after_a_failed_one_go_back_to_pending():
    plan = TaskPlan.build(['One', 'Two', 'Three'])
    second = plan.steps[1]
    plan.run(plan.steps[0].ident)
    plan.verify(plan.steps[0].ident)
    plan.run(second.ident)
    plan.fail(second.ident, 'no')
    plan.retry(second.ident)
    assert plan.steps[2].state == StepState.PENDING


def test_cancelling_leaves_the_finished_steps_alone():
    plan = TaskPlan.build(['One', 'Two'])
    plan.verify(plan.steps[0].ident)
    plan.cancel_remaining('the owner stopped it')
    assert plan.steps[0].state == StepState.VERIFIED
    assert plan.steps[1].state == StepState.CANCELLED


def test_the_summary_counts_the_steps_and_invents_no_percentage():
    plan = TaskPlan.build(['One', 'Two', 'Three'])
    plan.verify(plan.steps[0].ident)
    plan.fail(plan.steps[1].ident, 'no')
    text = plan.summary()
    assert '1. One — verified' in text
    assert '2. Two — failed: no' in text
    assert 'State: 1 verified, 1 failed, 1 pending.' in text
    assert '%' not in text
    assert 'percent' not in text.casefold()


def test_the_summary_never_shows_a_percentage_even_mid_plan():
    plan = TaskPlan.build(['One', 'Two', 'Three', 'Four'])
    plan.run(plan.steps[0].ident)
    text = plan.summary()
    assert '%' not in text


def test_a_plan_survives_a_round_trip_through_storage():
    plan = TaskPlan.build(['One', 'Two'])
    plan.verify(plan.steps[0].ident, 'done')
    restored = TaskPlan.from_dict(plan.as_dict())
    assert [step.state for step in restored.steps] == [
        StepState.VERIFIED, StepState.PENDING]
    assert restored.steps[0].detail == 'done'


# ── in the application ──────────────────────────────────────────────────────

def test_the_owner_sees_the_state_of_every_step(window, monkeypatch):
    launches = []
    monkeypatch.setattr('desktop.app.launch_app', lambda app: launches.append(app) or 'Launch requested')
    send(window, '/do open Notepad then open Calculator')
    window.finish_chat_launch(True)
    app = QApplication.instance()
    app.processEvents()
    card = window.plan_text.text()
    assert '1. Open Notepad — verified' in card
    assert 'verified' in card
    assert '%' not in card
    assert not window.plan_card.isHidden()


def test_a_failed_step_offers_to_be_tried_again(window, monkeypatch):
    monkeypatch.setattr('desktop.app.launch_app', lambda _: 'Launch requested')
    send(window, '/do open Notepad then open Calculator')
    window.finish_chat_launch(False)  # the owner declines: the plan is cancelled
    app = QApplication.instance()
    app.processEvents()
    # A declined step is not a failure, so there is nothing to try again.
    assert not window.plan_retry_button.isVisibleTo(window)


def test_the_state_of_a_plan_is_kept_when_the_window_closes(tmp_path, monkeypatch):
    """The owner comes back to a plan they can still act on."""
    from desktop.conversation_plan import PLAN_KEY

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    monkeypatch.setattr(window, 'get_key', lambda *_: pytest.fail('No AI call'))
    monkeypatch.setattr('desktop.app.launch_app', lambda _: 'Launch requested')
    try:
        window.prompt.setPlainText('/do open Notepad then open Calculator')
        window.send()
        window.finish_chat_launch(True)
        app.processEvents()
        task = plan_task(window)
        assert task is not None
        saved = window.store.get(PLAN_KEY + task['id'])
        assert saved is not None
        assert saved['steps'][0]['state'] == StepState.VERIFIED
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()

    again = Window(tmp_path)
    try:
        task = plan_task(again)
        assert task is not None
        saved = again.store.get(PLAN_KEY + task['id'])
        assert saved is not None
        assert saved['steps'][0]['label'] == 'Open Notepad'
    finally:
        again.close()
        again.deleteLater()
        app.processEvents()


def test_a_failed_step_is_tried_again_without_running_the_first_one_again(
        window, monkeypatch):
    """The whole point: a retry does not do the finished work a second time."""
    launches = []

    def launch(name):
        launches.append(name)
        if name == 'Calculator':
            raise RuntimeError('App unavailable')
        return 'Launch requested'

    monkeypatch.setattr('desktop.app.launch_app', launch)
    send(window, '/do open Notepad then open Calculator')
    # The first step is approved and it works.
    window.finish_chat_launch(True)
    assert launches == ['Notepad']
    # The second step fails.
    window.finish_chat_launch(True)
    assert launches == ['Notepad', 'Calculator']
    assert window.conversation_plan.active is None
    # The owner is offered the step again, and the plan card says so.
    assert window.plan_retry_button.isVisibleTo(window)
    assert 'failed' in window.plan_text.text()

    # The owner tries the failed step again.
    window.retry_failed_plan_step()
    assert window.conversation_plan.active is not None
    # The step that already worked is still verified, and it is not queued.
    assert 'verified' in window.plan_text.text()
    assert window.chat_launch is not None
    assert window.chat_launch[0] == 'Calculator'

    # The owner approves the retry, and only the failed step runs again.
    window.finish_chat_launch(True)
    assert launches == ['Notepad', 'Calculator', 'Calculator']
    assert launches.count('Notepad') == 1, 'the step that already worked ran again'
