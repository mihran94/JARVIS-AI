"""Offline tests for the local provider boundary.

The local model is the only provider allowed in offline mode, so these tests
pin the two properties that matter: it never reaches the network, and it never
receives a key.
"""
import json

import httpx
import pytest

from providers.chat import ProviderError
from providers.ollama import TAGS_LIMIT, is_loopback, probe_model_listing, stream_local
from providers.router import ProviderRouter


def openai_style_stream(content='வணக்கம்'):
    return (
        'data: ' + json.dumps({'choices': [{'delta': {'content': content}}]}) + '\n\n' +
        'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]}) + '\n\n' +
        'data: [DONE]\n\n'
    )


def test_loopback_detection():
    assert is_loopback('http://127.0.0.1:11434/v1/chat/completions') is True
    assert is_loopback('http://localhost:11434/v1/chat/completions') is True
    assert is_loopback('http://192.168.1.10:11434/v1/chat/completions') is False
    assert is_loopback('http://ollama.example.com/v1/chat/completions') is False


def test_a_remote_address_is_refused():
    with pytest.raises(ProviderError):
        stream_local('qwen3:8b', [{'role': 'user', 'content': 'Hi'}], lambda: None,
                     lambda _: None, endpoint='http://192.168.1.10:11434/v1/chat/completions')


def test_the_local_provider_never_sends_a_key():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=openai_style_stream(),
                              headers={'content-type': 'text/event-stream'})

    pieces = []
    result = stream_local('qwen3:8b', [{'role': 'user', 'content': 'Hi'}], lambda: None,
                          pieces.append, transport=httpx.MockTransport(handler))

    assert result == 'வணக்கம்'
    assert pieces == ['வணக்கம்']
    assert 'authorization' not in requests[0].headers
    assert str(requests[0].url) == 'http://127.0.0.1:11434/v1/chat/completions'
    body = json.loads(requests[0].content)
    assert body['model'] == 'qwen3:8b'
    assert body['stream'] is True


def test_offline_selection_reaches_the_local_adapter():
    router = ProviderRouter()
    spec = router.select('Ollama', configured=('Ollama',), offline_only=True)
    assert spec.local is True

    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=openai_style_stream(),
                              headers={'content-type': 'text/event-stream'})

    result = router.stream(spec, 'qwen3:8b', 'a-key-that-must-not-be-sent',
                            [{'role': 'user', 'content': 'Hi'}], lambda: None, lambda _: None,
                            transport=httpx.MockTransport(handler))

    assert result == 'வணக்கம்'
    assert 'authorization' not in requests[0].headers


def test_offline_selection_never_picks_a_cloud_provider():
    router = ProviderRouter()
    spec = router.select('OpenAI', configured=('OpenAI', 'Ollama'), allow_fallback=True,
                          offline_only=True)
    assert spec.name == 'Ollama'


@pytest.mark.parametrize('entry', [{'name': 'qwen3:8b'}, {'model': 'qwen3:8b'}])
def test_model_listing_uses_one_read_only_loopback_request(entry):
    def handler(request):
        requests.append(request)
        assert request.method == 'GET'
        assert str(request.url) == 'http://127.0.0.1:11434/api/tags'
        assert request.headers['accept-encoding'] == 'identity'
        assert 'authorization' not in request.headers and request.content == b''
        return httpx.Response(200, json={'models': [entry]})

    requests = []
    ok, detail = probe_model_listing('qwen3:8b', transport=httpx.MockTransport(handler))
    assert ok and 'generation was not tested' in detail
    assert len(requests) == 1


@pytest.mark.parametrize('response,message', [
    (httpx.Response(200, json={'models': []}), 'exact requested tag'),
    (httpx.Response(200, json={'models': [{'name': 'qwen3:4b'}]}), 'exact requested tag'),
    (httpx.Response(200, json={'models': [{'name': 'qwen3:8b'}, None]}), 'invalid model listing'),
    (httpx.Response(200, json={'models': {}}), 'invalid model listing'),
    (httpx.Response(200, content=b'not JSON'), 'invalid model listing'),
    (httpx.Response(200, content=b' ' * (TAGS_LIMIT + 1)), 'size limit'),
    (httpx.Response(200, headers={'Content-Encoding': 'private-unknown'}), 'encoding'),
    (httpx.Response(302, headers={'Location': 'https://example.invalid/private'}), 'HTTP 302'),
])
def test_listing_failures_are_distinct_and_redirects_are_not_followed(response, message):
    def handler(request):
        requests.append(request)
        return response

    requests = []
    ok, detail = probe_model_listing('qwen3:8b', transport=httpx.MockTransport(handler))
    assert not ok and message in detail
    assert 'private' not in detail and len(requests) == 1


@pytest.mark.parametrize('error,message', [
    (httpx.ConnectError, 'Could not reach'), (httpx.ReadTimeout, 'timed out'),
])
def test_listing_network_errors_are_not_leaked(error, message):
    def handler(_):
        raise error('private details')
    ok, detail = probe_model_listing('qwen3:8b', transport=httpx.MockTransport(handler))
    assert not ok and message in detail and 'private' not in detail


def test_blank_model_does_not_make_request():
    def handler(_):
        pytest.fail('blank tag made a network request')
    assert not probe_model_listing(' ', transport=httpx.MockTransport(handler))[0]


def test_ollama_operations_disable_environment_proxies_and_redirects(monkeypatch):
    calls = []
    original = httpx.Client

    def client(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(httpx, 'Client', client)
    probe_model_listing('local:tag', transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={'models': []})))
    stream_local('local:tag', [], lambda: None, lambda _: None,
                 transport=httpx.MockTransport(
                     lambda _: httpx.Response(200, text=openai_style_stream())))
    assert len(calls) == 2
    assert all(call['trust_env'] is False and call['follow_redirects'] is False for call in calls)
