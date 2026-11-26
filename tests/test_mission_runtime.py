"""The mission runtime: a bounded loop that cannot do what it was not told to.

WHAT IS COVERED
    * A mission that needs no tool answers straight away.
    * A read-only tool runs, and its real result goes back to the model.
    * A tool that changes something asks the owner first, and a refused
      tool never runs.
    * A tool that is not in the catalogue does not exist.
    * Arguments that do not match the schema are refused.
    * An answer that cannot be read stops the mission after two tries.
    * A mission cannot run for ever: the step limit ends it.
    * An emergency stop cancels the mission.
    * A tool that failed is never counted as evidence, and the mission
      never says that something happened that did not happen.
"""
import json

import pytest

from core.mission import (
    AgentRuntime, MissionError, parse_decision,
)
from core.mission_tools import Tool, ToolError, ToolRegistry
from core.store import Store
from agents.gateway import Gateway
from security.policy import Policy, Stopped


def tool_call(name, arguments=None, thought='Looking at it.'):
    return json.dumps({'action': 'tool', 'tool': name,
                       'arguments': arguments or {}, 'thought': thought})


def final_answer(text='The work is done.', thought='That is enough.'):
    return json.dumps({'action': 'answer', 'answer': text, 'thought': thought})


class FakePlanner:
    """A model that answers what the test tells it to answer."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, messages):
        self.calls.append(messages)
        if not self.answers:
            return final_answer('There is nothing left to do.')
        answer = self.answers.pop(0)
        return answer(messages) if callable(answer) else answer


@pytest.fixture
def policy():
    return Policy()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'history.sqlite3')


@pytest.fixture
def gateway(policy, store):
    return Gateway(policy, store)


@pytest.fixture
def registry():
    registry = ToolRegistry()
    registry.register(Tool(
        name='read_thing',
        description='Read a thing.',
        parameters={'type': 'object', 'properties': {'name': {'type': 'string'}},
                    'required': ['name']},
        read_only=True,
        run=lambda arguments: f'thing {arguments.get("name")} is here',
    ))
    registry.register(Tool(
        name='change_thing',
        description='Change a thing.',
        parameters={'type': 'object', 'properties': {}},
        read_only=False,
        run=lambda arguments: 'the thing changed',
    ))
    registry.register(Tool(
        name='broken_thing',
        description='A thing that fails.',
        parameters={'type': 'object', 'properties': {}},
        read_only=True,
        run=lambda arguments: (_ for _ in ()).throw(ToolError('It is not there.')),
    ))
    return registry


def runtime_for(registry, gateway, planner, **kwargs):
    return AgentRuntime(registry, gateway, planner, **kwargs)


# ── the simple paths ───────────────────────────────────────────────────────

def test_a_mission_that_needs_no_tool_answers_straight_away(registry, gateway):
    planner = FakePlanner([final_answer('Nothing needed doing.')])
    mission = runtime_for(registry, gateway, planner).run('Say hello.')
    assert mission.status == 'completed'
    assert mission.answer == 'Nothing needed doing.'
    assert mission.tools_used == []
    assert mission.steps == 1


def test_a_mission_needs_a_goal(registry, gateway):
    with pytest.raises(MissionError):
        runtime_for(registry, gateway, FakePlanner([])).run('   ')


def test_a_read_only_tool_runs_and_its_result_goes_back_to_the_model(registry, gateway):
    planner = FakePlanner([tool_call('read_thing', {'name': 'blue'}), final_answer('It is blue.')])
    mission = runtime_for(registry, gateway, planner).run('What colour is the thing?')
    assert mission.status == 'completed'
    assert mission.answer == 'It is blue.'
    assert len(mission.tools_used) == 1
    assert mission.tools_used[0]['tool'] == 'read_thing'
    assert 'thing blue is here' in mission.tools_used[0]['result']
    # The model saw the real result before it answered.
    last = planner.calls[-1][-1]['content']
    assert 'thing blue is here' in last


def test_the_mission_records_what_really_ran(registry, gateway):
    planner = FakePlanner([tool_call('read_thing', {'name': 'blue'}), final_answer('Done.')])
    mission = runtime_for(registry, gateway, planner).run('Look.')
    assert [item['tool'] for item in mission.evidence] == ['read_thing']


# ── approval ───────────────────────────────────────────────────────────────

def test_a_tool_that_changes_something_asks_the_owner_first(registry, gateway):
    asked = []

    def confirm(action):
        asked.append(action)
        return True

    planner = FakePlanner([tool_call('change_thing'), final_answer('It changed.')])
    mission = runtime_for(registry, gateway, planner).run('Change the thing.', confirm=confirm)
    assert mission.status == 'completed'
    assert len(asked) == 1
    assert asked[0].kind == 'mission_tool'
    assert 'change_thing' in asked[0].target
    assert mission.tools_used[0]['tool'] == 'change_thing'


def test_a_tool_that_changes_something_never_runs_without_a_way_to_ask(registry, gateway):
    planner = FakePlanner([tool_call('change_thing'), final_answer('It changed.')])
    mission = runtime_for(registry, gateway, planner).run('Change the thing.')
    assert mission.status == 'failed'
    assert mission.tools_used == []
    assert 'Nothing could be approved' in ' '.join(event.label for event in mission.events)


def test_a_refused_tool_is_never_run(registry, gateway):
    ran = []

    def refuse(action):
        return False

    registry.register(Tool(
        name='recording_thing',
        description='Change a thing and record it.',
        parameters={'type': 'object', 'properties': {}},
        read_only=False,
        run=lambda arguments: ran.append(arguments),
    ))
    planner = FakePlanner([tool_call('recording_thing'), final_answer('It changed.')])
    mission = runtime_for(registry, gateway, planner).run('Change the thing.', confirm=refuse)
    assert mission.status == 'failed'
    assert ran == []
    assert mission.tools_used == []
    assert 'did not allow' in ' '.join(event.label for event in mission.events)


def test_a_read_only_tool_does_not_ask_the_owner(registry, gateway):
    asked = []

    def confirm(action):
        asked.append(action)
        return True

    planner = FakePlanner([tool_call('read_thing', {'name': 'x'}), final_answer('Done.')])
    runtime_for(registry, gateway, planner).run('Look.', confirm=confirm)
    assert asked == []


# ── the refusals ───────────────────────────────────────────────────────────

def test_a_tool_that_is_not_in_the_catalogue_does_not_exist(registry, gateway):
    planner = FakePlanner([tool_call('run_shell', {'command': 'rm -rf /'})])
    mission = runtime_for(registry, gateway, planner).run('Delete everything.')
    assert mission.status == 'failed'
    assert mission.tools_used == []
    assert 'does not exist' in ' '.join(event.label for event in mission.events)


def test_arguments_that_do_not_match_the_schema_are_refused(registry, gateway):
    planner = FakePlanner([
        tool_call('read_thing', {'name': 'blue', 'extra': 'nope'}),
        final_answer('I could not read it.'),
    ])
    mission = runtime_for(registry, gateway, planner).run('Look at the thing.')
    assert mission.status == 'completed'
    assert mission.tools_used == []
    refused = [event for event in mission.events if event.kind == 'error']
    assert refused and 'does not take' in refused[0].detail
    # The model was told why, so it could correct itself.
    assert 'does not take the argument extra' in planner.calls[-1][-1]['content']


def test_a_tool_that_fails_is_not_counted_as_evidence(registry, gateway):
    planner = FakePlanner([tool_call('broken_thing'), final_answer('It was not there.')])
    mission = runtime_for(registry, gateway, planner).run('Read the broken thing.')
    assert mission.tools_used == []
    assert 'not there' in planner.calls[-1][-1]['content']


def test_a_tool_that_raises_something_unexpected_ends_the_mission(registry, gateway):
    def explode(arguments):
        raise RuntimeError('A secret internal detail.')

    registry.register(Tool(
        name='exploding_thing',
        description='A thing that fails in an unexpected way.',
        parameters={'type': 'object', 'properties': {}},
        read_only=True,
        run=explode,
    ))
    planner = FakePlanner([tool_call('exploding_thing')])
    mission = runtime_for(registry, gateway, planner).run('Look.')
    assert mission.status == 'failed'
    assert mission.tools_used == []
    # The internal detail is not shown to the owner.
    assert 'secret internal detail' not in json.dumps(mission.as_dict())


# ── the bounds ─────────────────────────────────────────────────────────────

def test_an_answer_that_cannot_be_read_stops_the_mission_after_two_turns(registry, gateway):
    planner = FakePlanner(['I would rather just talk about it.', 'Still talking.'])
    mission = runtime_for(registry, gateway, planner).run('Do something.')
    assert mission.status == 'failed'
    assert mission.steps == 2
    errors = [event for event in mission.events
              if event.label == 'The answer could not be read']
    assert len(errors) == 2


def test_a_mission_cannot_run_for_ever(registry, gateway):
    planner = FakePlanner([tool_call('read_thing', {'name': str(index)})
                            for index in range(10)])
    mission = runtime_for(registry, gateway, planner, max_steps=3).run('Look again and again.')
    assert mission.status == 'failed'
    assert mission.steps == 3
    assert len(mission.tools_used) == 3
    assert 'without a final answer' in mission.events[-1].detail


def test_an_emergency_stop_cancels_the_mission(registry, gateway):
    def stopped():
        raise Stopped('Emergency stop.')

    planner = FakePlanner([tool_call('read_thing', {'name': 'x'}), final_answer('Done.')])
    mission = runtime_for(registry, gateway, planner, check=stopped).run('Look.')
    assert mission.status == 'cancelled'
    assert mission.tools_used == []
    assert mission.events[-1].kind == 'cancelled'


def test_a_stop_between_the_steps_keeps_the_evidence_that_was_gathered(registry, gateway):
    state = {'calls': 0}

    def stop_after_one():
        # Check before planning, after planning, before dispatch and after the tool.
        state['calls'] += 1
        if state['calls'] > 4:
            raise Stopped('Emergency stop.')

    planner = FakePlanner([tool_call('read_thing', {'name': 'x'}), final_answer('Done.')])
    mission = runtime_for(registry, gateway, planner, check=stop_after_one).run('Look.')
    assert mission.status == 'cancelled'
    assert len(mission.tools_used) == 1


# ── the event stream ───────────────────────────────────────────────────────

def test_the_events_come_out_in_the_order_they_happened(registry, gateway):
    planner = FakePlanner([tool_call('read_thing', {'name': 'blue'}), final_answer('Done.')])
    mission = runtime_for(registry, gateway, planner).run('Look.')
    kinds = [event.kind for event in mission.events]
    assert kinds[0] == 'goal'
    assert 'tool' in kinds
    assert 'result' in kinds
    assert kinds[-1] == 'answer'
    assert kinds.index('tool') < kinds.index('result') < kinds.index('answer')


def test_the_caller_sees_the_events_while_the_mission_runs(registry, gateway):
    seen = []
    planner = FakePlanner([tool_call('read_thing', {'name': 'blue'}), final_answer('Done.')])
    runtime = runtime_for(registry, gateway, planner, on_event=seen.append)
    runtime.run('Look.')
    assert [event.kind for event in seen][-1] == 'answer'


# ── reading the model's answer ─────────────────────────────────────────────

def test_a_json_object_is_read():
    decision, problem = parse_decision('{"action": "answer", "answer": "Hello."}')
    assert problem is None
    assert decision['action'] == 'answer'
    assert decision['answer'] == 'Hello.'


def test_a_fenced_json_object_is_read():
    decision, problem = parse_decision('```json\n{"action": "answer", "answer": "Hello."}\n```')
    assert problem is None
    assert decision['answer'] == 'Hello.'


def test_a_json_object_after_a_word_is_read():
    decision, problem = parse_decision('Sure, here it is: {"action": "answer", "answer": "Hello."}')
    assert problem is None
    assert decision['answer'] == 'Hello.'


def test_prose_without_an_object_is_refused():
    decision, problem = parse_decision('I would rather talk about the weather.')
    assert decision is None
    assert 'JSON object' in problem


def test_an_unknown_action_is_refused():
    decision, problem = parse_decision('{"action": "delete_everything"}')
    assert decision is None
    assert 'must be "tool", "answer" or "skip"' in problem


def test_an_empty_answer_is_refused():
    decision, problem = parse_decision('{"action": "answer", "answer": "   "}')
    assert decision is None
    assert 'empty' in problem


def test_arguments_that_are_not_an_object_are_refused():
    decision, problem = parse_decision('{"action": "tool", "tool": "read_thing", "arguments": "blue"}')
    assert decision is None
    assert 'not an object' in problem


def test_expired_approval_cannot_dispatch(registry, gateway, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr('core.mission.time.monotonic', lambda: clock[0])
    name = next(name for name in registry.names() if not registry.get(name).read_only)
    tool = registry.get(name)
    called = []
    monkeypatch.setattr(type(tool), 'summary', lambda self, args: self.name)

    def approve(action):
        clock[0] = 9999.0
        called.append(action)
        return True

    args = {key: 'x' for key in tool.parameters.get('required', [])}
    planner = FakePlanner([tool_call(name, args)])
    mission = runtime_for(registry, gateway, planner).run('Work', confirm=approve)
    assert called and mission.status == 'failed'
    assert 'time limit' in mission.events[-1].detail
    assert not mission.tools_used
