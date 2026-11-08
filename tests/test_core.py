import json
import sys
from pathlib import Path
import httpx
import pytest

from agents.gateway import Gateway
from automation.windows import launch_app
from core.store import Store
from developer_studio.workspace import Workspace
from providers.chat import stream_chat, ProviderError, PROVIDERS
from security.policy import Policy, Action, Denied, Stopped
from security.vault import Vault


def test_approval_is_bound_and_one_use():
    policy = Policy()
    action = Action('save', 'one.py', 'digest')
    token = policy.approve(action, lambda _: True)
    with pytest.raises(Denied):
        policy.execute(Action('save', 'two.py', 'digest'), token, lambda: None)
    with pytest.raises(Denied):
        policy.execute(action, token, lambda: None)
    token = policy.approve(action, lambda _: True)
    assert policy.execute(action, token, lambda: 42) == 42
    with pytest.raises(Denied):
        policy.execute(action, token, lambda: None)


def test_stop_invalidates_old_work_after_resume():
    policy = Policy()
    ticket = policy.ticket()
    action = Action('launch', 'Notepad')
    token = policy.approve(action, lambda _: True)
    policy.stop()
    with pytest.raises(Stopped):
        policy.ticket()
    policy.resume()
    with pytest.raises(Stopped):
        policy.check(ticket)
    with pytest.raises(Denied):
        policy.execute(action, token, lambda: None)
    policy.check(policy.ticket())


def test_stop_during_approval():
    policy = Policy()
    def confirm(_):
        policy.stop()
        policy.resume()
        return True
    with pytest.raises(Stopped):
        policy.approve(Action('launch', 'Notepad'), confirm)


def test_gateway_decline_never_runs(tmp_path):
    store = Store(tmp_path / 'db')
    gateway = Gateway(Policy(), store)
    ran = []
    with pytest.raises(Denied):
        gateway.run(Action('launch', 'Notepad'), lambda _: False, lambda: ran.append(True))
    assert not ran
    assert store.tasks()[0]['status'] == 'denied'


def test_gateway_records_success_and_failure(tmp_path):
    store = Store(tmp_path / 'db')
    gateway = Gateway(Policy(), store)
    assert gateway.run(Action('test', 'ok'), lambda _: True, lambda: 'done') == 'done'
    with pytest.raises(ValueError):
        gateway.run(Action('test', 'bad'), lambda _: True,
                    lambda: (_ for _ in ()).throw(ValueError('bad')))
    assert [r['status'] for r in store.tasks()] == ['failed', 'completed']


def test_store_recovers_history(tmp_path):
    path = tmp_path / 'db'
    first = Store(path)
    ident = first.task('chat', 'provider')
    first.finish(ident, 'running')
    first.message('one', 'user', 'வணக்கம்')
    first.set('model', 'example')
    second = Store(path)
    assert second.tasks()[0]['status'] == 'interrupted'
    assert second.messages('one')[0]['content'] == 'வணக்கம்'
    assert second.get('model') == 'example'
    second.clear_messages('one')
    assert second.messages('one') == []


@pytest.mark.parametrize('name', [
    '../escape.py', '/tmp/x', 'C:/x', 'a:stream', 'a/../../x',
    '..\\x', 'CON.txt', 'dir/NUL', '.env', 'trailing.', 'a//b', 'bad?.txt',
])
def test_workspace_rejects_unsafe_paths(tmp_path, name):
    with pytest.raises(ValueError):
        Workspace(tmp_path).save(name, 'bad')


def test_workspace_blocks_symlink_escape(tmp_path):
    root = tmp_path / 'workspace'
    outside = tmp_path / 'outside'
    outside.mkdir()
    space = Workspace(root)
    try:
        (root / 'link').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Symlink privilege unavailable')
    with pytest.raises(ValueError):
        space.save('link/a.py', 'bad')
    assert not (outside / 'a.py').exists()


def test_workspace_backup_and_syntax_no_execution(tmp_path):
    space = Workspace(tmp_path)
    space.save('src/main.py', 'old')
    space.save('src/main.py', 'new')
    assert space.read('src/main.py') == 'new'
    assert next((tmp_path / '.revisions').iterdir()).read_text() == 'old'
    assert 'not executed' in space.check_python('raise RuntimeError("must never run")')
    with pytest.raises(SyntaxError):
        space.check_python('def broken(')


def stream_data(content='Hello', finish='stop'):
    return (
        'data: ' + json.dumps({'choices': [{'delta': {'content': content}}]}) + '\n\n' +
        'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': finish}]}) + '\n\n' +
        'data: [DONE]\n\n'
    )


@pytest.mark.parametrize('provider', list(PROVIDERS))
def test_provider_stream_contract(provider):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=stream_data('வணக்கம்'), headers={'content-type': 'text/event-stream'})
    pieces = []
    result = stream_chat(provider, 'test-model', 'test-secret', [{'role': 'user', 'content': 'Hi'}],
                         lambda: None, pieces.append, httpx.MockTransport(handler))
    assert result == 'வணக்கம்' and pieces == ['வணக்கம்']
    assert str(requests[0].url) == PROVIDERS[provider].endpoint
    assert requests[0].headers['authorization'] == 'Bearer test-secret'
    body = json.loads(requests[0].content)
    assert body['stream'] is True and body['model'] == 'test-model'
    assert 'tools' not in body


@pytest.mark.parametrize('status', [301, 401, 403, 429, 500])
def test_http_errors_redact_body(status):
    transport = httpx.MockTransport(lambda _: httpx.Response(status, text='sensitive-secret'))
    with pytest.raises(ProviderError) as error:
        stream_chat('OpenAI', 'model', 'secret', [], lambda: None, lambda _: None, transport)
    assert 'sensitive' not in str(error.value)
    assert str(status) in str(error.value)


@pytest.mark.parametrize('body', [
    'data: invalid\n\n',
    'data: {"error":{"message":"secret"}}\n\n',
    'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
    stream_data('partial', 'length'),
    'data: [DONE]\n\n',
])
def test_malformed_or_incomplete_stream_fails(body):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=body))
    with pytest.raises(ProviderError):
        stream_chat('OpenAI', 'model', 'secret', [], lambda: None, lambda _: None, transport)


def test_cancellation_prevents_request():
    calls = []
    policy = Policy()
    ticket = policy.ticket()
    policy.stop()
    with pytest.raises(Stopped):
        stream_chat('OpenAI', 'model', 'secret', [], lambda: policy.check(ticket), lambda _: None,
                    httpx.MockTransport(lambda r: calls.append(r)))
    assert not calls


def test_unknown_app_denied():
    with pytest.raises(ValueError):
        launch_app('powershell.exe -Command bad')


def test_vault_fails_closed_outside_windows():
    if sys.platform == 'win32':
        pytest.skip('Windows vault checked in acceptance tests')
    with pytest.raises(RuntimeError):
        Vault().put('OpenAI', 'test-only')
