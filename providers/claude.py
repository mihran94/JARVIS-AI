"""Native Anthropic (Claude) chat adapter.

Claude does not speak the OpenAI chat shape. It uses the Anthropic Messages
API: a different endpoint, a different authentication header, a mandatory
`max_tokens`, a top level `system` field instead of a system message, and a
different streaming event format.

The boundaries match the rest of the application: fixed trusted endpoint, no
redirects, no hidden retries, no silent fallback to another provider, and a
sanitized error that never echoes the response body.
"""
import json
import time

import httpx

from providers.chat import ProviderError, TransientProviderError

ENDPOINT = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'
DEFAULT_MAX_TOKENS = 2048
REQUEST_LIMIT = 100_000
RESPONSE_LIMIT = 200_000
TIME_LIMIT_SECONDS = 180


def _split_system(messages):
    """Anthropic keeps the system prompt outside the message list."""
    system_parts = []
    conversation = []
    for message in messages:
        role = message.get('role')
        content = message.get('content')
        if not isinstance(content, str):
            raise ProviderError('Invalid provider response.')
        if role == 'system':
            system_parts.append(content)
        elif role in ('user', 'assistant'):
            conversation.append({'role': role, 'content': content})
        else:
            raise ProviderError('Invalid provider response.')
    return '\n\n'.join(system_parts), conversation


def stream_claude(model, key, messages, check, emit, max_tokens=DEFAULT_MAX_TOKENS,
                  transport=None, metrics=None, endpoint=ENDPOINT):
    """Stream one Claude answer as text.

    Raises `ProviderError` for anything the caller must act on, and
    `TransientProviderError` for a temporary service failure. Authentication
    failures are never treated as transient, so no caller may retry them
    without asking the owner first.
    """
    if not key:
        raise ProviderError('Configure an API key and model first.')
    if not model or not model.strip():
        raise ProviderError('Configure an API key and model first.')
    if len(json.dumps(messages, ensure_ascii=False)) > REQUEST_LIMIT:
        raise ProviderError('Conversation exceeds the 100,000-character limit. Start a new chat.')

    system, conversation = _split_system(messages)
    if not conversation:
        raise ProviderError('Configure an API key and model first.')

    payload = {
        'model': model.strip(),
        'max_tokens': int(max_tokens),
        'messages': conversation,
        'stream': True,
    }
    if system:
        payload['system'] = system
    headers = {
        'x-api-key': key,
        'anthropic-version': ANTHROPIC_VERSION,
        'content-type': 'application/json',
    }

    started = time.monotonic()
    total = 0
    finished = False
    parts = []
    try:
        check()
        with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
                          transport=transport) as client:
            with client.stream('POST', endpoint, headers=headers, json=payload) as response:
                if response.status_code in (502, 503, 504, 529):
                    raise TransientProviderError(
                        f'Claude temporarily unavailable (HTTP {response.status_code}).')
                if response.status_code in (401, 403):
                    raise ProviderError('Claude rejected the API key.')
                if response.status_code == 429:
                    raise ProviderError('Claude reported a quota or rate limit.')
                if response.status_code != 200:
                    raise ProviderError(
                        f'Claude HTTP {response.status_code}. Check key, model, quota and access.')
                for line in response.iter_lines():
                    check()
                    if time.monotonic() - started > TIME_LIMIT_SECONDS:
                        raise ProviderError('Generation exceeded the 180-second limit.')
                    if not line.startswith('data:'):
                        continue
                    data = line[5:].strip()
                    if not data or data == '[DONE]':
                        continue
                    try:
                        event = json.loads(data)
                    except ValueError:
                        raise ProviderError('Invalid provider response.') from None
                    if not isinstance(event, dict):
                        raise ProviderError('Invalid provider response.')
                    kind = event.get('type')
                    if kind == 'error':
                        raise ProviderError('Claude reported a streaming error.')
                    if kind == 'message_start':
                        usage = (event.get('message') or {}).get('usage')
                        if metrics is not None and isinstance(usage, dict):
                            _record(metrics, usage)
                        continue
                    if kind == 'content_block_delta':
                        delta = event.get('delta') or {}
                        text = delta.get('text')
                        if text is None:
                            continue
                        if not isinstance(text, str):
                            raise ProviderError('Unexpected provider content format.')
                        if not text:
                            continue
                        total += len(text)
                        if total > RESPONSE_LIMIT:
                            raise ProviderError('Response exceeded local size limit.')
                        parts.append(text)
                        emit(text)
                        continue
                    if kind == 'message_delta':
                        usage = event.get('usage')
                        if metrics is not None and isinstance(usage, dict):
                            _record(metrics, usage)
                        continue
                    if kind == 'message_stop':
                        finished = True
                check()
                if not finished or not parts:
                    raise ProviderError('Claude stream ended without a complete text answer.')
        return ''.join(parts)
    except (ProviderError,):
        raise
    except httpx.TimeoutException:
        raise TransientProviderError('Claude timed out. Check connectivity and try again.') from None
    except httpx.ConnectError:
        raise TransientProviderError('Claude connection failed.') from None
    except httpx.HTTPError:
        raise ProviderError('Secure provider connection failed.') from None
    except (ValueError, KeyError, TypeError, IndexError, AttributeError):
        raise ProviderError('Invalid provider response.') from None


def _record(metrics, usage):
    """Map Anthropic usage names onto the shared metric names."""
    pairs = (('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens'))
    for source, target in pairs:
        count = usage.get(source)
        if type(count) is int and 0 <= count <= 1_000_000_000:
            metrics[target] = count
    prompt = metrics.get('prompt_tokens')
    completion = metrics.get('completion_tokens')
    if type(prompt) is int and type(completion) is int:
        metrics['total_tokens'] = prompt + completion
