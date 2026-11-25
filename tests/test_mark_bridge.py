import sys

import pytest

from core.store import Store
from developer_studio.projects import SavedProject, save_projects
from scripts import mark_bridge


def test_pc_action_requires_a_matching_preview(tmp_path, monkeypatch):
    store = Store(tmp_path / 'history.sqlite3')
    called = []
    monkeypatch.setattr(mark_bridge, 'execute', lambda _store, prepared: called.append(
        prepared['action']['target']) or 'Verified 391 in Calculator.')
    arguments = {'operation': 'calculate', 'value': '17 * 23'}
    preview = mark_bridge.handle(store, {'mode': 'prepare', 'arguments': arguments})
    assert preview['target'] == '17 * 23'
    assert called == []
    with pytest.raises(ValueError, match='no longer matches'):
        mark_bridge.handle(store, {'mode': 'execute', 'digest': preview['digest'],
                                   'arguments': {'operation': 'calculate', 'value': '17 * 24'}})
    assert called == []
    assert mark_bridge.handle(store, {'mode': 'execute', 'arguments': arguments,
                                     'digest': preview['digest']})['result'] == 'Verified 391 in Calculator.'
    assert called == ['17 * 23']


def test_saved_projects_list_and_changed_test_command(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    save_projects(store, [SavedProject('demo', str(tmp_path), test_command='python -m pytest')])
    result = mark_bridge.handle(store, {'mode': 'prepare', 'arguments': {'operation': 'projects'}})
    assert result == {'result': 'Saved JARVIS projects: demo'}
    request = {'mode': 'prepare', 'arguments': {'operation': 'project_test', 'value': 'demo'}}
    preview = mark_bridge.handle(store, request)
    assert 'python -m pytest' in preview['target']
    save_projects(store, [SavedProject('demo', str(tmp_path), test_command='python -m unittest')])
    with pytest.raises(ValueError, match='no longer matches'):
        mark_bridge.handle(store, dict(request, mode='execute', digest=preview['digest']))


def test_unlisted_application_and_unregistered_project_are_refused(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    with pytest.raises(ValueError, match='Notepad or Calculator'):
        mark_bridge.prepare(store, {'operation': 'open_app', 'value': 'powershell'})
    with pytest.raises(ValueError, match='not saved'):
        mark_bridge.prepare(store, {'operation': 'project_inspect', 'value': str(tmp_path)})


def test_one_verified_project_test_run(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    (tmp_path / 'test_demo.py').write_text(
        'import unittest\n\n'
        'class Demo(unittest.TestCase):\n'
        '    def test_add(self):\n'
        '        self.assertEqual(17 * 23, 391)\n', encoding='utf-8',
    )
    command = f'"{sys.executable}" -m unittest discover'
    save_projects(store, [SavedProject('demo', str(tmp_path), test_command=command)])
    request = {'mode': 'prepare', 'arguments': {'operation': 'project_test', 'value': 'demo'}}
    preview = mark_bridge.handle(store, request)
    response = mark_bridge.handle(store, dict(request, mode='execute', digest=preview['digest']))
    assert response == {'result': 'Project demo: tests passed.'}
