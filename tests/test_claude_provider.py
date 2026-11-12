"""Offline tests for the native Claude adapter.

The transport is a mock, so no API key is used and no request leaves the
machine.
"""
import json

import httpx
import pytest

from providers.chat import ProviderError, TransientProviderError
from providers.claude import stream_claude

MESSAGES = [
    {'role': 'system', 'content': 'Answer briefly.'},
    {'role': 'user', 'content': 'வணக்கம்'},
]


def claude_stream(pieces=('வணக்கம்', ' உலகம்')):
    events = [
        {'type': 'message_start', 'message': {'usage': {'input_tokens': 12, 'output_tokens': 0}}},
    ]
    for piece in pieces:
        events.append({'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': piece}})
    events.append({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'},
                   'usage': {'output_tokens': 7}})
    events.append({'type': 'message_stop'})
    return ''.join('data: ' + json.dumps(event) + '\n\n' for event in events)


def test_claude_request_uses_the_native_shape():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=claude_stream(),
                              headers={'content-type': 'text/event-stream'})

    pieces = []
    result = stream_claude('claude-test', 'test-secret', MESSAGES, lambda: None, pieces.append,
                            transport=httpx.MockTransport(handler))

    assert result == 'வணக்கம் உலகம்'
    assert pieces == ['வணக்கம்', ' உலகம்']
    assert str(requests[0].url) == 'https://api.anthropic.com/v1/messages'
    assert requests[0].headers['x-api-key'] == 'test-secret'
    assert requests[0].headers['anthropic-version'] == '2023-06-01'
    body = json.loads(requests[0].content)
    assert body['model'] == 'claude-test'
    assert body['stream'] is True
    assert body['max_tokens'] > 0
    # The system prompt is a top level field for Anthropic, not a message.
    assert body['system'] == 'Answer briefly.'
    assert [message['role'] for message in body['messages']] == ['user']


def test_claude_records_usage():
    metrics = {}
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, text=claude_stream(), headers={'content-type': 'text/event-stream'}))
    stream_claude('claude-test', 'test-secret', MESSAGES, lambda: None, lambda _: None,
                  transport=transport, metrics=metrics)
    assert metrics['prompt_tokens'] == 12
    assert metrics['completion_tokens'] == 7
    assert metrics['total_tokens'] == 19


def test_claude_authentication_failure_is_not_treated_as_transient():
    transport = httpx.MockTransport(lambda _: httpx.Response(401, text='sensitive-secret'))
    with pytest.raises(ProviderError) as error:
        stream_claude('claude-test', 'secret', MESSAGES, lambda: None, lambda _: None,
                      transport=transport)
    assert 'sensitive' not in str(error.value)
    assert not isinstance(error.value, TransientProviderError)


def test_claude_quota_failure_is_not_retried():
    transport = httpx.MockTransport(lambda _: httpx.Response(429, text='sensitive-secret'))
    with pytest.raises(ProviderError):
        stream_claude('claude-test', 'secret', MESSAGES, lambda: None, lambda _: None,
                      transport=transport)


def test_claude_service_failure_is_transient():
    transport = httpx.MockTransport(lambda _: httpx.Response(529, text='busy'))
    with pytest.raises(TransientProviderError):
        stream_claude('claude-test', 'secret', MESSAGES, lambda: None, lambda _: None,
                      transport=transport)


def test_claude_incomplete_stream_is_an_error():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, text='data: {"type": "content_block_delta", '
                                             '"delta": {"text": "partial"}}\n\n',
                                headers={'content-type': 'text/event-stream'}))
    with pytest.raises(ProviderError):
        stream_claude('claude-test', 'secret', MESSAGES, lambda: None, lambda _: None,
                      transport=transport)


def test_claude_reports_a_streaming_error_event():
    body = 'data: {"type": "error", "error": {"type": "overloaded_error"}}\n\n'
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, text=body, headers={'content-type': 'text/event-stream'}))
    with pytest.raises(ProviderError):
        stream_claude('claude-test', 'secret', MESSAGES, lambda: None, lambda _: None,
                      transport=transport)


def test_claude_requires_a_key():
    with pytest.raises(ProviderError):
        stream_claude('claude-test', '', MESSAGES, lambda: None, lambda _: None)
