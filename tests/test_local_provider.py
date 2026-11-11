"""Offline tests for the local provider boundary.

The local model is the only provider allowed in offline mode, so these tests
pin the two properties that matter: it never reaches the network, and it never
receives a key.
"""
import json

import httpx
import pytest

from providers.chat import ProviderError
from providers.ollama import is_loopback, stream_local
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
        stream_local('llama3.2', [{'role': 'user', 'content': 'Hi'}], lambda: None,
                     lambda _: None, endpoint='http://192.168.1.10:11434/v1/chat/completions')


def test_the_local_provider_never_sends_a_key():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=openai_style_stream(),
                              headers={'content-type': 'text/event-stream'})

    pieces = []
    result = stream_local('llama3.2', [{'role': 'user', 'content': 'Hi'}], lambda: None,
                          pieces.append, transport=httpx.MockTransport(handler))

    assert result == 'வணக்கம்'
    assert pieces == ['வணக்கம்']
    assert 'authorization' not in requests[0].headers
    assert str(requests[0].url) == 'http://127.0.0.1:11434/v1/chat/completions'
    body = json.loads(requests[0].content)
    assert body['model'] == 'llama3.2'
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

    result = router.stream(spec, 'llama3.2', 'a-key-that-must-not-be-sent',
                            [{'role': 'user', 'content': 'Hi'}], lambda: None, lambda _: None,
                            transport=httpx.MockTransport(handler))

    assert result == 'வணக்கம்'
    assert 'authorization' not in requests[0].headers


def test_offline_selection_never_picks_a_cloud_provider():
    router = ProviderRouter()
    spec = router.select('OpenAI', configured=('OpenAI', 'Ollama'), allow_fallback=True,
                          offline_only=True)
    assert spec.name == 'Ollama'
