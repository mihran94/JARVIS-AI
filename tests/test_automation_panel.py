"""The Automation page and the proposed actions on it.

WHAT IS COVERED
    * A proposed action is a card with Run, Edit and Dismiss.
    * Run passes the action on, Edit passes the owner's changed values,
      and Dismiss says the action is not to be done.
    * The browser, Suggestion Mode, Work on this, Any App Control and
      the task activity are all on this one page.
    * The card says the action exactly, and the digest is shown.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from desktop.automation_panel import AutomationPanel, ProposedAction


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app):
    return AutomationPanel()


def test_a_proposed_action_is_a_card(panel):
    action = ProposedAction(kind='mission_tool', target='type_notepad(text=...)')
    card = panel.propose(action)
    assert panel.cards() == [card]
    assert card.run_button.text() == 'Run'
    assert card.edit_button.text() == 'Edit'
    assert card.dismiss_button.text() == 'Dismiss'


def test_run_passes_the_action_on(panel):
    ran = []
    panel.action_run.connect(lambda action, values: ran.append((action, values)))
    action = ProposedAction(kind='launch_app', target='Notepad')
    card = panel.propose(action)
    card.run_button.click()
    assert ran and ran[0][0] is action


def test_the_owner_can_change_the_action_before_it_runs(panel):
    ran = []
    panel.action_run.connect(lambda action, values: ran.append((action, values)))
    action = ProposedAction(kind='type_notepad', target='type_notepad',
                            editable={'text': 'On Friday.'})
    card = panel.propose(action)
    card.edit_button.click()
    assert card.editor.isHidden() is False
    card.fields['text'].setText('On Monday.')
    card.run_button.click()
    assert ran[0][1] == {'text': 'On Monday.'}


def test_dismiss_says_the_action_is_not_to_be_done(panel):
    dismissed = []
    panel.action_dismissed.connect(lambda action: dismissed.append(action))
    action = ProposedAction(kind='launch_app', target='Notepad')
    panel.propose(action)
    panel.cards()[0].dismiss_button.click()
    assert dismissed and dismissed[0] is action
    assert panel.cards() == []


def test_an_action_with_nothing_to_change_cannot_be_edited(panel):
    action = ProposedAction(kind='launch_app', target='Notepad')
    card = panel.propose(action)
    assert card.edit_button.isEnabled() is False


def test_the_digest_of_the_action_is_shown(panel):
    action = ProposedAction(kind='browser_open', target='https://example.com',
                            digest='abc123')
    card = panel.propose(action)
    assert 'abc123' in card.digest.text()


def test_the_browser_command_is_sent_from_the_page(panel):
    sent = []
    panel.browser_requested.connect(lambda command: sent.append(command))
    panel.browser_command.setText('open https://example.com')
    panel.browser_button.click()
    assert sent == ['open https://example.com']


def test_the_goal_is_sent_when_work_on_this_is_pressed(panel):
    goals = []
    panel.mission_requested.connect(lambda goal: goals.append(goal))
    panel.goal.setText('Open Notepad and write the report')
    panel.work_button.click()
    assert goals == ['Open Notepad and write the report']


def test_an_empty_goal_starts_nothing(panel):
    goals = []
    panel.mission_requested.connect(lambda goal: goals.append(goal))
    panel.work_button.click()
    assert goals == []


def test_the_suggestion_mode_is_shown(panel):
    panel.set_suggestion_mode(True)
    assert panel.suggestion_mode.isChecked() is True
    panel.set_suggestion_mode(False)
    assert panel.suggestion_mode.isChecked() is False


def test_the_task_activity_is_shown(panel):
    panel.set_activity('launch_app Notepad completed')
    assert 'launch_app' in panel.activity.toPlainText()


def test_the_open_applications_are_shown(panel):
    panel.set_windows('notepad.exe (pid=1234): \'Untitled - Notepad\'')
    assert 'pid=1234' in panel.windows.toPlainText()


def test_the_controls_of_an_inspected_application_are_shown(panel):
    panel.set_controls("Button 'Save' (id='saveButton')")
    assert 'saveButton' in panel.controls.toPlainText()
