"""V0.3 workflow and observation regression tests; no Windows launch occurs."""
import sqlite3

import pytest

from agents.gateway import Gateway
from agents.workflows import WorkflowQueue
from core.store import Store
from security.policy import Policy, Denied, Stopped
from automation.inspection import inspect_windows


def make_workflows(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    policy = Policy()
    return WorkflowQueue(store, Gateway(policy, store))


def test_workflow_requires_individual_approval(tmp_path):
    queue = make_workflows(tmp_path)
    ident = queue.add(['Notepad', 'Calculator'])
    approvals, launches = [], []
    def confirm(action):
        approvals.append(action.target)
        return True
    assert 'Completed 2' in queue.run(ident, confirm, lambda app: launches.append(app) or 'OK')
    assert launches == ['Notepad', 'Calculator']
    assert len(approvals) == 2
    assert [step['status'] for step in queue.steps(ident)] == ['completed', 'completed']
    assert queue.rows()[0]['status'] == 'completed'
    with pytest.raises(Denied):
        queue.run(ident, confirm, lambda _: pytest.fail('Replay prevented'))


def test_rejected_step_never_runs_or_starts_subsequent_steps(tmp_path):
    queue = make_workflows(tmp_path)
    ident = queue.add(['Notepad', 'Calculator'])
    launches = []
    with pytest.raises(Denied):
        queue.run(ident, lambda action: 'step 1/' not in action.target,
                  lambda app: launches.append(app))
    assert not launches
    assert [step['status'] for step in queue.steps(ident)] == ['denied', 'cancelled']
    assert queue.rows()[0]['status'] == 'denied'


def test_failure_stops_after_one_step(tmp_path):
    queue = make_workflows(tmp_path)
    ident = queue.add(['Notepad', 'Calculator', 'Notepad'])
    def launcher(app):
        if app == 'Calculator':
            raise RuntimeError('Failure')
        return 'OK'
    with pytest.raises(RuntimeError):
        queue.run(ident, lambda _: True, launcher)
    assert [s['status'] for s in queue.steps(ident)] == ['completed', 'failed', 'cancelled']
    assert queue.rows()[0]['status'] == 'failed'


def test_cancel_during_approval_prevents_launch(tmp_path):
    queue = make_workflows(tmp_path)
    ident = queue.add(['Notepad', 'Calculator'])
    def confirm(_):
        assert queue.cancel(ident)
        return True
    with pytest.raises(Stopped):
        queue.run(ident, confirm, lambda _: pytest.fail('Must not launch'))
    assert queue.rows()[0]['status'] == 'cancelled'


def test_emergency_stop_then_resume_cannot_continue(tmp_path):
    queue = make_workflows(tmp_path)
    ident = queue.add(['Notepad', 'Calculator'])
    seen = []
    def confirm(_):
        if not seen:
            queue.gateway.policy.stop()
            queue.cancel_pending()
            queue.gateway.policy.resume()
        return True
    with pytest.raises(Stopped):
        queue.run(ident, confirm, lambda app: seen.append(app))
    assert seen == []
    with pytest.raises(Denied):
        queue.run(ident, lambda _: True)


def test_invalid_workflows_and_tampering(tmp_path):
    queue = make_workflows(tmp_path)
    for items in ([], ['Notepad']*11, ['cmd.exe'], 'Notepad', ['Notepad', 'calc.exe']):
        with pytest.raises(ValueError):
            queue.add(items)
    ident = queue.add(['Notepad'])
    with queue.store.connect() as db:
        db.execute("UPDATE workflow_steps SET app='powershell.exe' WHERE workflow_id=?", (ident,))
    with pytest.raises(Denied):
        queue.run(ident, lambda _: True, lambda _: pytest.fail('Must not execute'))


def test_restart_marks_in_progress_workflow_interrupted(tmp_path):
    queue = make_workflows(tmp_path)
    ident = queue.add(['Notepad'])
    with queue.store.connect() as db:
        db.execute("UPDATE workflows SET status='running' WHERE id=?", (ident,))
        db.execute("UPDATE workflow_steps SET status='running' WHERE workflow_id=?", (ident,))
    restarted = make_workflows(tmp_path)
    assert restarted.rows()[0]['status'] == 'interrupted'
    assert restarted.steps(ident)[0]['status'] == 'interrupted'
    with pytest.raises(Denied):
        restarted.run(ident, lambda _: True)


def test_schema_v02_migration_backup(tmp_path):
    path = tmp_path / 'history.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY,session TEXT,role TEXT,content TEXT)')
        db.execute("INSERT INTO messages VALUES (1,'s','user','old data')")
        db.execute('PRAGMA user_version=2')
    store = Store(path)
    assert store.messages('s')[0]['content'] == 'old data'
    assert len(list(tmp_path.glob('history-pre-v03-*.sqlite3'))) == 1
    Store(path)
    assert len(list(tmp_path.glob('history-pre-v03-*.sqlite3'))) == 1


def test_inspector_rejects_non_windows():
    import sys
    if sys.platform != 'win32':
        with pytest.raises(RuntimeError):
            inspect_windows()
