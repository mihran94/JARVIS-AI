"""The engine router: local first, Gemini for the one step that needs it.

WHAT IS COVERED
    * The on-device model answers a step, and the step is recorded as
      answered on this computer.
    * A step the on-device model cannot complete is handed to Gemini only
      when the owner turned the automatic fallback on.
    * The reason for every fallback is recorded, in words the owner can
      read.
    * Only the context that the step needs is sent.
    * Protected files, screen content and microphone audio are named
      before they are shared, and a refusal blocks the step.
    * When Gemini is not available the step is blocked, the mission
      carries on with the parts the local model can do, and the owner is
      told what was blocked.
"""
import json

import pytest

from core.engines import (
    EngineRouter, EngineUnavailable, GEMINI, LOCAL, REASON_LOCAL_UNAVAILABLE,
    REASON_LOCAL_UNUSABLE, SHARED_FILE, SHARED_MICROPHONE, SHARED_SCREEN,
    classify_context, enabled_from_store, history_from_store, save_history_to_store,
    set_enabled_in_store, shared_note, step_context,
)
from core.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'history.sqlite3')


def router(**kwargs):
    """A router with a local engine that always answers."""
    calls = {'local': [], 'gemini': []}

    def local_stream(model, messages, check, emit):
        calls['local'].append(messages)
        return kwargs.pop('local_answer', '{"action": "answer", "answer": "Local."}')

    def gemini_stream(model, key, messages, check, emit):
        calls['gemini'].append(messages)
        return kwargs.pop('gemini_answer', '{"action": "answer", "answer": "Gemini."}')

    options = {'local_model': 'qwen3:8b', 'local_stream': local_stream,
               'gemini_model': 'gemini-3.5-flash-lite', 'gemini_key': 'key',
               'gemini_stream': gemini_stream}
    options.update(kwargs)
    engine = EngineRouter(**options)
    return engine, calls


def test_the_on_device_model_answers_the_step():
    engine, calls = router()
    text, record = engine.plan_step([{'role': 'user', 'content': 'hello'}])
    assert 'Local' in text
    assert record.engine == LOCAL
    assert record.used_gemini is False
    assert calls['gemini'] == []


def test_a_step_the_local_model_cannot_do_goes_to_gemini_when_it_is_allowed():
    engine, calls = router(gemini_enabled=True,
                            validate=lambda text: False)
    text, record = engine.plan_step([{'role': 'user', 'content': 'hello'}])
    assert record.engine == GEMINI
    assert record.reason == REASON_LOCAL_UNUSABLE
    assert 'could not complete' in record.explanation
    assert calls['gemini']


def test_without_the_toggle_a_step_the_local_model_cannot_do_stays_local():
    engine, calls = router(gemini_enabled=False, validate=lambda text: False)
    text, record = engine.plan_step([{'role': 'user', 'content': 'hello'}])
    assert record.engine == LOCAL
    assert calls['gemini'] == []


def test_a_local_model_that_cannot_be_reached_lets_gemini_answer():
    def broken(model, messages, check, emit):
        raise RuntimeError('connection refused')

    engine, calls = router(local_stream=broken, gemini_enabled=True)
    text, record = engine.plan_step([{'role': 'user', 'content': 'hello'}])
    assert record.engine == GEMINI
    assert record.reason == REASON_LOCAL_UNAVAILABLE
    assert 'could not be reached' in record.explanation


def test_when_gemini_is_not_configured_the_step_is_blocked():
    engine, calls = router(gemini_enabled=True, gemini_key='', validate=lambda text: False)
    with pytest.raises(EngineUnavailable) as problem:
        engine.plan_step([{'role': 'user', 'content': 'hello'}])
    assert 'Gemini is not available' in str(problem.value)
    assert problem.value.blocked is True


def test_only_the_context_that_the_step_needs_is_shared():
    engine, calls = router(gemini_enabled=True, validate=lambda text: False)
    messages = [
        {'role': 'system', 'content': 'the instructions'},
        {'role': 'user', 'content': 'the goal'},
        {'role': 'assistant', 'content': '{"action": "tool"}'},
        {'role': 'user', 'content': 'the first observation'},
        {'role': 'assistant', 'content': '{"action": "tool"}'},
        {'role': 'user', 'content': 'the second observation'},
        {'role': 'assistant', 'content': '{"action": "tool"}'},
        {'role': 'user', 'content': 'the newest observation'},
    ]
    engine.plan_step(messages)
    shared = calls['gemini'][0]
    assert shared[0] == {'role': 'system', 'content': 'the instructions'}
    assert shared[1] == {'role': 'user', 'content': 'the goal'}
    assert len(shared) == 6
    assert shared[-1]['content'] == 'the newest observation'
    assert 'the first observation' not in json.dumps(shared)


def test_the_step_context_keeps_the_instructions_the_goal_and_the_recent_steps():
    messages = [
        {'role': 'system', 'content': 'the instructions'},
        {'role': 'user', 'content': 'the goal'},
        {'role': 'assistant', 'content': '{"action": "tool"}'},
        {'role': 'user', 'content': 'an old observation'},
        {'role': 'assistant', 'content': '{"action": "tool"}'},
        {'role': 'user', 'content': 'a newer observation'},
    ]
    context = step_context(messages, keep=1)
    assert [item['content'] for item in context] == [
        'the instructions', 'the goal', '{"action": "tool"}', 'a newer observation']


def test_the_tool_catalogue_does_not_require_screen_sharing_approval():
    from core.mission import system_instructions
    from core.mission_tools import build_registry

    engine, calls = router(gemini_enabled=True, validate=lambda text: False,
                           approve_share=lambda *_: pytest.fail('No screen was read'))
    messages = [
        {'role': 'system', 'content': system_instructions(build_registry())},
        {'role': 'user', 'content': 'What is 19 times 29?'},
    ]
    assert 'observe_screen' in messages[0]['content']
    engine.plan_step(messages)
    assert calls['gemini']


def test_protected_data_stays_local_without_an_approval_handler():
    engine, calls = router(gemini_enabled=True, validate=lambda text: False)
    with pytest.raises(EngineUnavailable, match='not allowed'):
        engine.plan_step([{'role': 'user', 'content': 'A spoken phrase'}], voice=True)
    assert calls['gemini'] == []


def test_screen_content_is_named_before_it_is_shared():
    messages = [{'role': 'user',
                 'content': 'The result of observe_screen:\nThere is a password on screen.'}]
    assert SHARED_SCREEN in classify_context(messages)


def test_the_microphone_is_named_before_it_is_shared():
    messages = [{'role': 'user', 'content': 'the owner said hello'}]
    assert SHARED_MICROPHONE in classify_context(messages, voice=True)
    assert classify_context(messages) == ()


def test_a_protected_file_is_named_before_it_is_shared():
    messages = [{'role': 'user', 'content': 'the contents of .env'}]
    assert SHARED_FILE in classify_context(messages, protected_paths=['.env'])


def test_the_owner_is_asked_before_something_sensitive_is_shared():
    asked = []
    engine, calls = router(gemini_enabled=True, validate=lambda text: False,
                           approve_share=lambda kinds, note: asked.append((kinds, note)) or True)
    engine.plan_step([{'role': 'user', 'content': 'The result of observe_screen:\ntext'}])
    assert asked
    kinds, note = asked[0]
    assert SHARED_SCREEN in kinds
    assert SHARED_SCREEN in note


def test_a_refused_share_blocks_the_step_and_nothing_is_sent():
    engine, calls = router(gemini_enabled=True, validate=lambda text: False,
                           approve_share=lambda kinds, note: False)
    with pytest.raises(EngineUnavailable) as problem:
        engine.plan_step([{'role': 'user', 'content': 'The result of observe_screen:\ntext'}])
    assert 'not allowed' in str(problem.value)
    assert calls['gemini'] == []


def test_nothing_sensitive_is_asked_about_when_the_step_is_ordinary():
    asked = []
    engine, calls = router(gemini_enabled=True, validate=lambda text: False,
                           approve_share=lambda kinds, note: asked.append(kinds) or True)
    engine.plan_step([{'role': 'user', 'content': 'an ordinary request'}])
    assert asked == []


def test_every_step_is_recorded_with_the_engine_that_answered():
    engine, calls = router(gemini_enabled=True, validate=lambda text: False)
    engine.plan_step([{'role': 'user', 'content': 'one'}])
    engine.plan_step([{'role': 'user', 'content': 'two'}])
    assert [record.engine for record in engine.history] == [GEMINI, GEMINI]


def test_the_owners_choice_is_remembered(store):
    assert enabled_from_store(store) is False
    assert set_enabled_in_store(store, True) is True
    assert enabled_from_store(store) is True


def test_the_history_survives_a_restart(store):
    engine, calls = router(gemini_enabled=True, validate=lambda text: False)
    engine.plan_step([{'role': 'user', 'content': 'one'}])
    save_history_to_store(store, engine.history)
    saved = history_from_store(store)
    assert saved and saved[-1]['engine'] == GEMINI


def test_the_shared_note_names_what_would_be_shared():
    assert shared_note(()) == ''
    assert shared_note((SHARED_SCREEN,)) == SHARED_SCREEN
    assert 'and' in shared_note((SHARED_SCREEN, SHARED_MICROPHONE))
