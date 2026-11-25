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
TAGS_ENDPOINT = 'http://127.0.0.1:11434/api/tags'
LOOPBACK_HOSTS = ('127.0.0.1', '::1', 'localhost')
REQUEST_LIMIT = 100_000
RESPONSE_LIMIT = 200_000
TIME_LIMIT_SECONDS = 180
TAGS_LIMIT = 256 * 1024
TAGS_TIMEOUT = 2.0


def is_loopback(url: str) -> bool:
    """True when the URL points at this machine."""
    try:
        host = (urlparse(url).hostname or '').lower()
    except ValueError:
        return False
    return host in LOOPBACK_HOSTS


def _local_client(*, timeout, transport):
    return httpx.Client(timeout=timeout, transport=transport, trust_env=False,
                        follow_redirects=False)


def probe_model_listing(model, *, transport=None):
    """Check an exact tag with one read-only request, not a generation request."""
    model = model.strip()
    if not model:
        return False, 'An exact local model tag is required.'
    try:
        with _local_client(timeout=TAGS_TIMEOUT, transport=transport) as client:
            with client.stream('GET', TAGS_ENDPOINT,
                               headers={'Accept-Encoding': 'identity'}) as response:
                if response.status_code != 200:
                    return False, f'Local Ollama listing returned HTTP {response.status_code}.'
                if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                    return False, 'Local Ollama returned an unsupported listing encoding.'
                contents = bytearray()
                for chunk in response.iter_bytes():
                    if len(contents) + len(chunk) > TAGS_LIMIT:
                        return False, 'Local Ollama model listing exceeded the size limit.'
                    contents.extend(chunk)
        payload = json.loads(contents.decode('utf-8'))
    except httpx.TimeoutException:
        return False, 'Local Ollama model listing timed out.'
    except httpx.HTTPError:
        return False, 'Could not reach the local Ollama listing at 127.0.0.1:11434.'
    except (ValueError, RecursionError):
        return False, 'Local Ollama returned an invalid model listing.'

    models = payload.get('models') if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return False, 'Local Ollama returned an invalid model listing.'
    names = []
    for entry in models:
        name = (entry.get('name') or entry.get('model')) if isinstance(entry, dict) else None
        if not isinstance(name, str) or not name.strip():
            return False, 'Local Ollama returned an invalid model listing.'
        names.append(name)
    if model not in names:
        return False, 'The exact requested tag is not in the local Ollama listing.'
    return True, 'Local Ollama lists the exact tag. Text generation was not tested.'


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
        with _local_client(timeout=httpx.Timeout(30, connect=10), transport=transport) as client:
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
