"""Streaming text only. No model-generated tools are executed."""
from dataclasses import dataclass
import json
import time
import httpx
from security.policy import Stopped


@dataclass(frozen=True)
class Provider:
    endpoint: str
    default_model: str


PROVIDERS = {
    'OpenAI': Provider('https://api.openai.com/v1/chat/completions', 'gpt-4.1-mini'),
    'MiniMax': Provider('https://api.minimax.io/v1/chat/completions', 'MiniMax-M3'),
    'Gemini': Provider('https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
                       'gemini-2.5-flash'),
}


class ProviderError(RuntimeError):
    pass


class TransientProviderError(ProviderError):
    """A connection failure or temporary server failure; excludes auth and quota."""


def stream_chat(provider, model, key, messages, check, emit, transport=None, metrics=None):
    """Fixed trusted endpoints; no redirects, retry, or silent provider fallback."""
    if provider not in PROVIDERS:
        raise ProviderError('Unknown provider.')
    if not key or not model.strip():
        raise ProviderError('Configure an API key and model first.')
    if len(json.dumps(messages, ensure_ascii=False)) > 100_000:
        raise ProviderError('Conversation exceeds the 100,000-character limit. Start a new chat.')
    payload = {'model': model.strip(), 'messages': messages, 'stream': True,
               'stream_options': {'include_usage': True}}
    started = time.monotonic()
    total = 0
    finished = False
    parts = []
    try:
        check()
        with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
                          transport=transport) as client:
            with client.stream('POST', PROVIDERS[provider].endpoint,
                               headers={'Authorization': f'Bearer {key}'}, json=payload) as response:
                if response.status_code in (502, 503, 504):
                    raise TransientProviderError(f'{provider} temporarily unavailable (HTTP {response.status_code}).')
                if response.status_code != 200:
                    raise ProviderError(f'{provider} HTTP {response.status_code}. Check key, model, quota and access.')
                for line in response.iter_lines():
                    check()
                    if time.monotonic() - started > 180:
                        raise ProviderError('Generation exceeded the 180-second limit.')
                    if not line.startswith('data:'):
                        continue
                    data = line[5:].strip()
                    if data == '[DONE]':
                        finished = True
                        break
                    if not data:
                        continue
                    event = json.loads(data)
                    if 'error' in event:
                        raise ProviderError('Provider reported a streaming error.')
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
                            raise ProviderError('Provider ended without a complete answer (limit, filter or unsupported tool).')
                        finished = True
                    content = choices[0].get('delta', {}).get('content') or ''
                    if not isinstance(content, str):
                        raise ProviderError('Unexpected provider content format.')
                    if content:
                        total += len(content)
                        if total > 200_000:
                            raise ProviderError('Response exceeded local size limit.')
                        parts.append(content)
                        emit(content)
                check()
                if not finished or not parts:
                    raise ProviderError('Provider stream ended without a complete text answer.')
        return ''.join(parts)
    except (Stopped, ProviderError):
        raise
    except httpx.TimeoutException:
        raise TransientProviderError('Provider timed out. Check connectivity and try again.') from None
    except httpx.ConnectError:
        raise TransientProviderError('Provider connection failed.') from None
    except httpx.HTTPError:
        raise ProviderError('Secure provider connection failed.') from None
    except (ValueError, KeyError, TypeError, IndexError, AttributeError):
        raise ProviderError('Invalid provider response.') from None
