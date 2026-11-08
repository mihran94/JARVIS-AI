import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest

from agents.gateway import Gateway
from agents.queue import TaskQueue
from core.store import Store
from providers.chat import stream_chat
from security.policy import Policy, Denied, Stopped


def make_queue(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    return TaskQueue(store, Gateway(Policy(), store))


def test_waiting_job_survives_restart_but_needs_approval(tmp_path):
    queue = make_queue(tmp_path)
    ident = queue.add('Notepad')
    restarted = make_queue(tmp_path)
    calls = []
    with pytest.raises(Denied):
        restarted.run(ident, lambda _: False, calls.append)
    assert calls == []
    assert restarted.rows()[0]['status'] == 'denied'


def test_completed_job_cannot_run_again(tmp_path):
    queue = make_queue(tmp_path)
    ident = queue.add('Calculator')
    calls = []
    def launch(app):
        calls.append(app)
        return 'launched'
    assert queue.run(ident, lambda _: True, launch) == 'launched'
    with pytest.raises(Denied):
        queue.run(ident, lambda _: True, launch)
    assert calls == ['Calculator']
    assert queue.rows()[0]['status'] == 'completed'


def test_queue_cancel_during_confirmation(tmp_path):
    queue = make_queue(tmp_path)
    ident = queue.add('Notepad')
    def confirm(_):
        assert queue.cancel(ident)
        return True
    with pytest.raises(Stopped):
        queue.run(ident, confirm, lambda _: pytest.fail('Must not launch'))
    assert queue.rows()[0]['status'] == 'cancelled'


def test_queue_stop_invalidates_and_resume_does_not_restart(tmp_path):
    queue = make_queue(tmp_path)
    first, second = queue.add('Notepad'), queue.add('Calculator')
    def confirm(_):
        queue.gateway.policy.stop()
        queue.cancel_pending()
        queue.gateway.policy.resume()
        return True
    with pytest.raises(Stopped):
        queue.run(first, confirm, lambda _: pytest.fail('Must not launch'))
    assert {row['status'] for row in queue.rows()} == {'cancelled'}
    with pytest.raises(Denied):
        queue.run(second, lambda _: True)


def test_queue_claim_is_atomic(tmp_path):
    queue = make_queue(tmp_path)
    ident = queue.add('Notepad')
    calls = []
    def attempt(_):
        try:
            return queue.run(ident, lambda _: True, lambda app: calls.append(app) or 'done')
        except Denied:
            return 'denied'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(results) == ['denied', 'done']
    assert calls == ['Notepad']


@pytest.mark.parametrize('state', ['reviewing', 'running'])
def test_interrupted_job_never_replays(tmp_path, state):
    queue = make_queue(tmp_path)
    ident = queue.add('Notepad')
    with queue.store.connect() as db:
        db.execute('UPDATE jobs SET status=? WHERE id=?', (state, ident))
    restarted = make_queue(tmp_path)
    assert restarted.rows()[0]['status'] == 'interrupted'
    with pytest.raises(Denied):
        restarted.run(ident, lambda _: True)


def test_queue_revalidates_tampered_allowlist(tmp_path):
    queue = make_queue(tmp_path)
    ident = queue.add('Notepad')
    with queue.store.connect() as db:
        db.execute("UPDATE jobs SET app='powershell.exe' WHERE id=?", (ident,))
    with pytest.raises(Denied):
        queue.run(ident, lambda _: True, lambda _: pytest.fail('Must not launch'))


def test_failed_launch_is_not_retried(tmp_path):
    queue = make_queue(tmp_path)
    ident = queue.add('Notepad')
    def fail(_):
        raise RuntimeError('not installed')
    with pytest.raises(RuntimeError):
        queue.run(ident, lambda _: True, fail)
    assert queue.rows()[0]['status'] == 'failed'
    with pytest.raises(Denied):
        queue.run(ident, lambda _: True, fail)


def test_v01_migration_makes_backup_and_preserves_history(tmp_path):
    path = tmp_path / 'history.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY,session TEXT,role TEXT,content TEXT)')
        db.execute("INSERT INTO messages VALUES (1,'s','user','old conversation')")
    store = Store(path)
    assert store.messages('s')[0]['content'] == 'old conversation'
    backup = list(tmp_path.glob('history-pre-v02-*.sqlite3'))
    assert len(backup) == 1
    with sqlite3.connect(backup[0]) as db:
        assert db.execute('SELECT content FROM messages').fetchone()[0] == 'old conversation'
        assert db.execute('PRAGMA user_version').fetchone()[0] == 0
    Store(path)
    assert len(list(tmp_path.glob('history-pre-v02-*'))) == 1


def test_newer_database_version_rejected(tmp_path):
    path = tmp_path / 'db'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA user_version=99')
    with pytest.raises(RuntimeError):
        Store(path)


def test_provider_usage_empty_choices_captured(tmp_path):
    usage = {'prompt_tokens': 7, 'completion_tokens': 4, 'total_tokens': 11}
    events = [
        {'choices': [{'delta': {'content': 'OK'}}]},
        {'choices': [], 'usage': usage},
    ]
    body = ''.join('data: ' + json.dumps(x) + '\n\n' for x in events) + 'data: [DONE]\n\n'
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, text=body)
    metrics = {}
    assert stream_chat('OpenAI', 'test', 'fake', [], lambda: None, lambda _: None,
                       httpx.MockTransport(handle), metrics=metrics) == 'OK'
    assert metrics == usage
    assert requests[0]['stream_options'] == {'include_usage': True}
    store = Store(tmp_path / 'db')
    store.record_usage('id', 'OpenAI', 'test', 'completed', metrics)
    assert store.usage_rows()[0]['total_tokens'] == 11


def test_usage_missing_is_unknown_not_zero(tmp_path):
    store = Store(tmp_path / 'db')
    store.record_usage('id', 'Gemini', 'test', 'cancelled', {})
    assert store.usage_rows()[0]['total_tokens'] is None


def test_invalid_usage_counts_ignored():
    body = ('data: {"choices":[{"delta":{"content":"OK"}}],'
            '"usage":{"prompt_tokens":-2,"completion_tokens":true,"total_tokens":"9"}}\n\n'
            'data: [DONE]\n\n')
    metrics = {}
    stream_chat('OpenAI', 'test', 'fake', [], lambda: None, lambda _: None,
                httpx.MockTransport(lambda _: httpx.Response(200, text=body)), metrics=metrics)
    assert metrics == {}


def test_sessions_and_usage_persist(tmp_path):
    store = Store(tmp_path / 'db')
    store.message('one', 'user', 'Hello')
    store.message('two', 'user', 'Bonjour')
    store.record_usage('t', 'OpenAI', 'test', 'completed', {'duration_ms': 12, 'total_tokens': 8})
    reopened = Store(tmp_path / 'db')
    assert [s['session'] for s in reopened.sessions()] == ['two', 'one']
    assert reopened.usage_rows()[0]['duration_ms'] == 12
