"""Local Ollama adapter.

Ollama runs on this machine. The adapter only talks to the loopback
interface, never sends an API key and never leaves the host. A non loopback
address is refused, so a local provider cannot be turned into an open relay
by pointing it at a remote port.

The request shape is the OpenAI compatible one that Ollama exposes.
"""
import json
import time
from urllib.parse import urlparse

import httpx

from providers.chat import ProviderError, TransientProviderError

DEFAULT_ENDPOINT = 'http://127.0.0.1:11434/v1/chat/completions'
LOOPBACK_HOSTS = ('127.0.0.1', '::1', 'localhost')
REQUEST_LIMIT = 100_000
RESPONSE_LIMIT = 200_000
TIME_LIMIT_SECONDS = 180


def is_loopback(url: str) -> bool:
    """True when the URL points at this machine."""
    try:
        host = (urlparse(url).hostname or '').lower()
    except ValueError:
        return False
    return host in LOOPBACK_HOSTS


def stream_local(model, messages, check, emit, endpoint=DEFAULT_ENDPOINT, transport=None,
                  metrics=None):
    """Stream one answer from the local model."""
    if not model or not model.strip():
        raise ProviderError('Configure a model first.')
    if not is_loopback(endpoint):
        raise ProviderError('The local provider may only use the loopback interface.')
    if len(json.dumps(messages, ensure_ascii=False)) > REQUEST_LIMIT:
        raise ProviderError('Conversation exceeds the 100,000-character limit. Start a new chat.')

    payload = {'model': model.strip(), 'messages': messages, 'stream': True}
    started = time.monotonic()
    total = 0
    finished = False
    parts = []
    try:
        check()
        with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
                          transport=transport) as client:
            with client.stream('POST', endpoint, json=payload) as response:
                if response.status_code in (502, 503, 504):
                    raise TransientProviderError(
                        f'The local model temporarily unavailable (HTTP {response.status_code}).')
                if response.status_code != 200:
                    raise ProviderError(
                        f'The local model returned HTTP {response.status_code}. '
                        'Check that Ollama is running and the model is installed.')
                for line in response.iter_lines():
                    check()
                    if time.monotonic() - started > TIME_LIMIT_SECONDS:
                        raise ProviderError('Generation exceeded the 180-second limit.')
                    if not line.startswith('data:'):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    if data == '[DONE]':
                        finished = True
                        break
                    event = json.loads(data)
                    if 'error' in event:
                        raise ProviderError('The local model reported a streaming error.')
                    usage = event.get('usage')
                    if metrics is not None and isinstance(usage, dict):
                        for name in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                            count = usage.get(name)
                            if type(count) is int and 0 <= count <= 1_000_000_000:
                                metrics[name] = count
                    choices = event.get('choices', [])
                    if not choices:
                        continue
                    reason = choices[0].get('finish_reason')
                    if reason:
                        if reason != 'stop':
                            raise ProviderError(
                                'The local model ended without a complete answer.')
                        finished = True
                    content = choices[0].get('delta', {}).get('content') or ''
                    if not isinstance(content, str):
                        raise ProviderError('Unexpected provider content format.')
                    if content:
                        total += len(content)
                        if total > RESPONSE_LIMIT:
                            raise ProviderError('Response exceeded local size limit.')
                        parts.append(content)
                        emit(content)
                check()
                if not finished or not parts:
                    raise ProviderError('The local model ended without a complete text answer.')
        return ''.join(parts)
    except (ProviderError,):
        raise
    except httpx.TimeoutException:
        raise TransientProviderError('The local model timed out.') from None
    except httpx.ConnectError:
        raise TransientProviderError('The local model connection failed.') from None
    except httpx.HTTPError:
        raise ProviderError('Secure provider connection failed.') from None
    except (ValueError, KeyError, TypeError, IndexError, AttributeError):
        raise ProviderError('Invalid provider response.') from None
