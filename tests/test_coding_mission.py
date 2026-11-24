"""A coding request that JARVIS works through itself.

WHAT IS COVERED
    * The mission uses the coding tools, and the approval boundary is
      used for every change.
    * A mission that ends with the tests passing is reported as verified.
    * A mission that leaves the tests failing goes through the repair
      loop, and the repair that really fixes it is reported as verified.
    * A mission that leaves the tests failing and cannot fix them is
      reported as failed, with the real failure.
    * The proposal the model prepares is read from its JSON, and prose
      is not.
    * A change that is refused changes nothing.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import json
import sys

import pytest

from agents.gateway import Gateway
from core.coding_mission import CodingMission, parse_proposal
from core.store import Store
from security.policy import Policy


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'app.py').write_text('VALUE = 1\n', encoding='utf-8')
    (root / 'test_app.py').write_text(
        'from app import VALUE\n\n\ndef test_value():\n    assert VALUE == 2\n',
        encoding='utf-8')
    return root


def build(project, answers, *, confirm=None, test_command=None):
    """A coding mission with a model that answers what the test says."""
    policy = Policy()
    store = Store(project / 'history.sqlite3')
    gateway = Gateway(policy, store)
    remaining = list(answers)

    def planner(messages):
        if remaining:
            return remaining.pop(0)
        return json.dumps({'action': 'answer', 'answer': 'The tests pass now.',
                           'thought': 'Done.'})

    mission = CodingMission(
        project, 'fix the failing test', planner=planner, gateway=gateway,
        confirm=confirm if confirm is not None else (lambda action: True),
        test_command=test_command or f'{sys.executable} -m pytest -q')
    return mission


# ── the proposal ───────────────────────────────────────────────────────────

def test_a_proposal_is_read_from_json():
    proposal = parse_proposal('{"action": "write", "path": "a.py", "content": "x"}')
    assert proposal == {'action': 'write', 'path': 'a.py', 'content': 'x'}


def test_a_fenced_proposal_is_read():
    proposal = parse_proposal('```json\n{"action": "patch", "patch": "--- a"}\n```')
    assert proposal['action'] == 'patch'


def test_prose_is_not_a_proposal():
    assert parse_proposal('I think you should change the value to 2.') is None
    assert parse_proposal('') is None
    assert parse_proposal(None) is None


def test_a_proposal_with_the_wrong_shape_is_refused():
    assert parse_proposal('{"action": "delete", "path": "a.py"}') is None
    assert parse_proposal('{"action": "write", "path": 5}') is None


# ── the mission ────────────────────────────────────────────────────────────

def test_a_mission_that_fixes_the_test_is_verified(project):
    answers = [
        json.dumps({'action': 'tool', 'tool': 'read_file',
                    'arguments': {'path': 'app.py'}, 'thought': 'Look first.'}),
        json.dumps({'action': 'tool', 'tool': 'write_file',
                    'arguments': {'path': 'app.py', 'content': 'VALUE = 2\n'},
                    'thought': 'The value is wrong.'}),
        json.dumps({'action': 'answer', 'answer': 'I changed app.py.', 'thought': 'Done.'}),
    ]
    mission = build(project, answers)
    result = mission.run()
    assert result.status == 'verified', result.summary
    assert [entry['tool'] for entry in result.mission.tools_used] == ['read_file', 'write_file']
    assert (project / 'app.py').read_text(encoding='utf-8') == 'VALUE = 2\n'


def test_a_mission_that_leaves_the_test_failing_is_reported_as_failed(project):
    answers = [
        json.dumps({'action': 'tool', 'tool': 'write_file',
                    'arguments': {'path': 'app.py', 'content': 'VALUE = 3\n'},
                    'thought': 'A guess.'}),
        json.dumps({'action': 'answer', 'answer': 'I changed app.py.', 'thought': 'Done.'}),
    ]
    mission = build(project, answers)
    result = mission.run()
    assert result.status in ('failed', 'blocked')
    assert result.summary
    # The real failure is reported, not a promise that it worked.
    assert result.repair is not None
    assert result.repair.failures or 'did not say why' in result.repair.message


def test_the_repair_loop_fixes_a_test_the_mission_missed(project):
    """The mission changes the wrong file; the repair fixes the right one."""
    answers = [
        json.dumps({'action': 'tool', 'tool': 'write_file',
                    'arguments': {'path': 'notes.txt', 'content': 'not the fix\n'},
                    'thought': 'A guess.'}),
        json.dumps({'action': 'answer', 'answer': 'I looked.', 'thought': 'Done.'}),
        json.dumps({'action': 'write', 'path': 'app.py', 'content': 'VALUE = 2\n'}),
    ]
    mission = build(project, answers)
    result = mission.run()
    assert result.status == 'verified', result.summary
    assert (project / 'app.py').read_text(encoding='utf-8') == 'VALUE = 2\n'


def test_a_refused_change_changes_nothing(project):
    before = (project / 'app.py').read_text(encoding='utf-8')
    answers = [
        json.dumps({'action': 'tool', 'tool': 'write_file',
                    'arguments': {'path': 'app.py', 'content': 'VALUE = 9\n'},
                    'thought': 'A guess.'}),
    ]
    mission = build(project, answers, confirm=lambda action: False)
    result = mission.run()
    assert (project / 'app.py').read_text(encoding='utf-8') == before
    assert result.status in ('failed', 'blocked')


def test_the_approval_names_the_file_that_is_written(project):
    asked = []
    answers = [
        json.dumps({'action': 'tool', 'tool': 'write_file',
                    'arguments': {'path': 'app.py', 'content': 'VALUE = 2\n'},
                    'thought': 'A fix.'}),
        json.dumps({'action': 'answer', 'answer': 'Done.', 'thought': 'Done.'}),
    ]
    mission = build(project, answers, confirm=lambda action: asked.append(action) or True)
    mission.run()
    assert asked
    assert 'app.py' in asked[0].target


def test_the_mission_stays_inside_the_project(project, tmp_path):
    answers = [
        json.dumps({'action': 'tool', 'tool': 'write_file',
                    'arguments': {'path': '../outside.py', 'content': 'x'},
                    'thought': 'A guess.'}),
        json.dumps({'action': 'answer', 'answer': 'Done.', 'thought': 'Done.'}),
    ]
    mission = build(project, answers)
    result = mission.run()
    assert not (tmp_path / 'outside.py').exists()
    assert result.status in ('verified', 'failed', 'blocked', 'cancelled')


def test_the_mission_reports_its_steps(project):
    answers = [
        json.dumps({'action': 'tool', 'tool': 'list_files', 'arguments': {},
                    'thought': 'Look around.'}),
        json.dumps({'action': 'answer', 'answer': 'I looked.', 'thought': 'Done.'}),
    ]
    mission = build(project, answers)
    result = mission.run()
    assert result.steps
    assert any('list_files' in step for step in result.steps)
