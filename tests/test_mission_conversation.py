"""A goal that comes from the conversation reaches the mission runtime.

WHAT IS COVERED
    * /mission and the Work on this button both send the goal to the
      mission runtime instead of to the plain chat.
    * The goal is kept in the conversation, and the answer comes back
      into the same conversation when the mission finishes.
    * A mission that did not finish says so in the conversation instead
      of pretending to have an answer.
    * An ordinary message still goes to the ordinary chat.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import json
import time

import httpx
import pytest
from PySide6.QtWidgets import QApplication

from core.conversation import mission_argument
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


def final(text):
    return json.dumps({'action': 'answer', 'answer': text, 'thought': 'That is it.'})


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    app = QApplication.instance()
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


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


# ── the command ────────────────────────────────────────────────────────────

def test_the_mission_command_takes_the_goal_after_it():
    assert mission_argument('/mission find the launch date') == 'find the launch date'
    assert mission_argument('/task find the launch date') == 'find the launch date'


def test_the_mission_command_needs_a_goal():
    assert mission_argument('/mission') == ''
    assert mission_argument('/mission   ') == ''


def test_an_ordinary_message_is_not_a_mission():
    assert mission_argument('what is the weather') is None
    assert mission_argument('tell me about the mission') is None


# ── the routing ────────────────────────────────────────────────────────────

def test_a_mission_command_reaches_the_mission_runtime(window):
    connect(window, [final('The launch is on Friday.')])
    window.prompt.setPlainText('/mission when is the launch')
    window.send()
    assert wait_for(lambda: window.mission_panel.status.text() == 'COMPLETE')
    assert window.mission_panel.evidence_column.answer.text() == 'The launch is on Friday.'
    # The goal and the answer are both in the conversation.
    messages = window.store.messages(window.session)
    assert messages[-2] == {'role': 'user', 'content': 'when is the launch'}
    assert messages[-1]['role'] == 'assistant'
    assert 'Friday' in messages[-1]['content']


def test_the_work_on_this_button_sends_the_message_as_a_mission(window):
    connect(window, [final('Notepad is open.')])
    window.mission_mode.setChecked(True)
    window.prompt.setPlainText('open notepad for me')
    window.send()
    assert wait_for(lambda: window.mission_panel.status.text() == 'COMPLETE')
    assert window.store.messages(window.session)[-1]['role'] == 'assistant'


def test_a_mission_that_failed_says_so_in_the_conversation(window):
    connect(window, [json.dumps({'action': 'tool', 'tool': 'no_such_tool',
                                  'arguments': {}, 'thought': 'Trying.'})])
    window.prompt.setPlainText('/mission do the impossible')
    window.send()
    assert wait_for(lambda: window.mission_panel.status.text() == 'FAILED')
    reply = window.store.messages(window.session)[-1]
    assert reply['role'] == 'assistant'
    assert 'did not finish' in reply['content'] or 'stopped' in reply['content'].lower()


def test_an_ordinary_message_still_goes_to_the_chat(window):
    connect(window, [final('This should not be a mission.')])
    window.prompt.setPlainText('hello there')
    window.send()
    assert wait_for(lambda: window.worker is None and window.store.messages(window.session))
    assert window.mission_panel.status.text() == 'READY'
    # The ordinary chat stored what the provider said, word for word.
    # The mission path would have unwrapped the envelope instead.
    stored = window.store.messages(window.session)[-1]['content']
    assert 'This should not be a mission.' in stored
    assert stored.startswith('{"action"')
