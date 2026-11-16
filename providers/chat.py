"""Streaming text only. No model-generated tools are executed."""
from dataclasses import dataclass
import json
import time
import httpx
from providers.errors import BACKUP_ELIGIBLE_KINDS, Diagnosis, FailureKind, diagnose
from security.policy import Stopped


@dataclass(frozen=True)
class Provider:
    endpoint: str
    default_model: str


GEMINI_RECOMMENDED_MODEL = 'gemini-3.5-flash-lite'


PROVIDERS = {
    'OpenAI': Provider('https://api.openai.com/v1/chat/completions', 'gpt-6-luna'),
    'MiniMax': Provider('https://api.minimax.io/v1/chat/completions', 'MiniMax-M3.1-Flash'),
    'DeepSeek': Provider('https://api.deepseek.com/chat/completions', 'deepseek-flash'),
    'Groq': Provider('https://api.groq.com/openai/v1/chat/completions', 'openai/gpt-oss-120b'),
    'OpenRouter': Provider('https://openrouter.ai/api/v1/chat/completions', 'openai/gpt-6-luna'),
    'Gemini': Provider('https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
                       GEMINI_RECOMMENDED_MODEL),
}


class ProviderError(RuntimeError):
    pass


class ProviderFailure(ProviderError):
    """A provider failure that carries a classified diagnosis.

    The message is the diagnosis written for a human, so the same failure
    reads the same in a message box, in the usage log and in a screenshot.
    The diagnosis itself is available for anything that needs the kind.
    """

    def __init__(self, diagnosis):
        if isinstance(diagnosis, str):
            super().__init__(diagnosis)
            self.diagnosis = None
            return
        super().__init__(f'{diagnosis.title}. {diagnosis.message} {diagnosis.hint}')
        self.diagnosis = diagnosis

    @property
    def kind(self):
        """The failure kind, or None for a failure that was not classified."""
        return self.diagnosis.kind if self.diagnosis else None


class TransientProviderError(ProviderFailure):
    """A connection failure or temporary server failure; excludes auth and quota."""


def _raise_for_status(provider, response, model):
    """Turn a failed HTTP answer into a classified failure.

    The body is read so the failure can be classified, and it is never passed
    on: a provider can echo the key back, and the message ends up on screen.
    """
    body = ''
    try:
        body = response.read().decode('utf-8', 'replace')
    except Exception:
        body = ''
    diagnosis = diagnose(provider, status=response.status_code, body=body, model=model,
                         recommended=PROVIDERS[provider].default_model)
    if diagnosis.kind in BACKUP_ELIGIBLE_KINDS:
        raise TransientProviderError(diagnosis) from None
    raise ProviderFailure(diagnosis) from None


def _transport_failure(provider, error, model):
    """Classify a failure that never reached an HTTP status."""
    diagnosis = diagnose(provider, error=error, model=model)
    if diagnosis.kind in BACKUP_ELIGIBLE_KINDS:
        return TransientProviderError(diagnosis)
    return ProviderFailure(diagnosis)


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
                if response.status_code != 200:
                    _raise_for_status(provider, response, model.strip())
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
    except httpx.TimeoutException as exc:
        raise _transport_failure(provider, exc, model.strip()) from None
    except httpx.ConnectError as exc:
        raise _transport_failure(provider, exc, model.strip()) from None
    except httpx.HTTPError as exc:
        raise _transport_failure(provider, exc, model.strip()) from None
    except (ValueError, KeyError, TypeError, IndexError, AttributeError):
        raise ProviderError('Invalid provider response.') from None
