"""Check that the model the owner configured is one the provider actually serves.

WHAT THIS IS FOR
    The provider manager could tell the owner that a request FAILED. It could
    not tell them WHY a model ID did not work, because the only way to find out
    was to send a paid request and read the error.

    Every provider the owner can reach lists its own models. Asking that list
    is free, needs no generation, and answers the question exactly: is the
    model ID the owner typed one that this key can actually use?

    So this module asks the provider for its catalogue and compares.

HOW EACH PROVIDER IS ASKED
    * Gemini uses its own model list, `GET /v1beta/models`, with the key in
      the `x-goog-api-key` header. The answer names the models as
      `models/gemini-3.8-flash`, so the `models/` prefix is removed and only
      the models that support `generateContent` are kept.
    * The OpenAI compatible services use `GET .../models` with the key as a
      bearer token, which is the same shape for OpenAI, OpenRouter, Groq,
      DeepSeek, MiniMax and Ollama.
    * Claude uses `GET /v1/models` with the key in the `x-api-key` header.

WHAT THIS MODULE WILL NOT DO
    * It never sends a prompt, so it never costs a generation and never puts
      the owner's words on a provider's servers.
    * It never returns the key, and it never puts the key in a message. The
      failure it reports comes from the same classifier the chat path uses, so
      a key that the provider echoes back in an error body still cannot leak
      into a message box or a screenshot.
    * It does not fail the check when a provider cannot list its models. Some
      deployments disable the listing, and "I could not check" is a different
      answer from "that model does not exist", and the caller is told which
      one it got.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from providers.errors import Diagnosis, diagnose


#: How long the catalogue request may take.
LIST_TIMEOUT = httpx.Timeout(20, connect=10)

#: The model list endpoint for each provider, and how the key is sent.
_MODEL_LISTS = {
    'Gemini': {
        'url': 'https://generativelanguage.googleapis.com/v1beta/models',
        'auth': 'header',
        'header': 'x-goog-api-key',
    },
    'Claude': {
        'url': 'https://api.anthropic.com/v1/models',
        'auth': 'header',
        'header': 'x-api-key',
    },
}

#: Providers whose chat endpoint ends in this suffix use the OpenAI shape.
_OPENAI_SUFFIX = '/chat/completions'


@dataclass(frozen=True)
class ModelAvailability:
    """The answer to "can this key use this model?"."""

    provider: str
    model: str
    available: bool
    #: True when the provider returned a catalogue, so the answer is definite.
    known: bool
    detail: str
    diagnosis: Diagnosis | None = None
    models: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict:
        """A plain dictionary for the HUD and for the usage log."""
        return {
            'provider': self.provider,
            'model': self.model,
            'available': self.available,
            'known': self.known,
            'detail': self.detail,
            'diagnosis': self.diagnosis.as_dict() if self.diagnosis else None,
            'models': list(self.models),
        }


def model_list_endpoint(provider: str, endpoint: str) -> str | None:
    """The catalogue URL for a provider, or None when it has no catalogue."""
    spec = _MODEL_LISTS.get(provider)
    if spec is not None:
        return spec['url']
    if endpoint.endswith(_OPENAI_SUFFIX):
        return endpoint[: -len(_OPENAI_SUFFIX)] + '/models'
    return None


def _headers(provider: str, key: str) -> dict:
    """The request headers, with the key in the header the provider expects."""
    spec = _MODEL_LISTS.get(provider)
    if spec is None:
        return {'Authorization': f'Bearer {key}'} if key else {}
    headers = {}
    if key:
        headers[spec['header']] = key
    if provider == 'Claude':
        headers['anthropic-version'] = '2023-06-01'
    return headers


def _normalise(model: str) -> str:
    """Remove the catalogue resource prefix while preserving the exact model ID."""
    text = str(model or '').strip()
    if text.startswith('models/'):
        text = text[len('models/'):]
    return text


def _parse_models(provider: str, payload) -> tuple[str, ...]:
    """Pull the model IDs out of a provider's catalogue answer."""
    names: list[str] = []
    if isinstance(payload, dict):
        entries = payload.get('models')
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    name = entry.get('name')
                    methods = entry.get('supportedGenerationMethods')
                    if isinstance(name, str) and name:
                        if isinstance(methods, list) and methods:
                            if 'generateContent' not in methods:
                                continue
                        names.append(name)
        data = payload.get('data')
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    name = entry.get('id') or entry.get('name')
                    if isinstance(name, str) and name:
                        names.append(name)
    elif isinstance(payload, list):
        for entry in payload:
            if isinstance(entry, dict):
                name = entry.get('id') or entry.get('name')
                if isinstance(name, str) and name:
                    names.append(name)
    unique = []
    for name in names:
        cleaned = _normalise(name)
        if cleaned and cleaned not in unique:
            unique.append(cleaned)
    return tuple(sorted(unique))


def list_models(provider: str, endpoint: str, key: str, transport=None) -> tuple[str, ...]:
    """The model IDs the provider serves for this key.

    Raises `ProviderError` on failure; use :func:`check_model` for the form
    that explains itself.
    """
    from providers.chat import ProviderError, ProviderFailure

    url = model_list_endpoint(provider, endpoint)
    if not url:
        raise ProviderError(f'{provider} does not publish a model list.')
    if provider != 'Ollama' and not str(key or '').strip():
        raise ProviderFailure(diagnose(provider, key=''))

    names = set()
    seen_tokens = set()
    params = {}
    try:
        with httpx.Client(timeout=LIST_TIMEOUT, follow_redirects=False,
                          transport=transport) as client:
            for _ in range(20):
                response = client.get(url, headers=_headers(provider, key), params=params)
                if response.status_code != 200:
                    raise ProviderFailure(diagnose(
                        provider, status=response.status_code, body=response.text))
                try:
                    payload = response.json()
                except ValueError:
                    raise ProviderError(f'{provider} returned an unreadable model list.') from None
                names.update(_parse_models(provider, payload))
                if provider == 'Gemini' and isinstance(payload, dict):
                    token = payload.get('nextPageToken')
                    parameter = 'pageToken'
                elif provider == 'Claude' and isinstance(payload, dict) and payload.get('has_more'):
                    token = payload.get('last_id')
                    parameter = 'after_id'
                    if not token:
                        raise ProviderError('The Claude catalogue omitted its next page cursor.')
                else:
                    token = None
                if not token:
                    return tuple(sorted(names))
                if not isinstance(token, str) or token in seen_tokens:
                    raise ProviderError(f'{provider} returned an invalid model list cursor.')
                seen_tokens.add(token)
                params = {parameter: token}
    except httpx.HTTPError as error:
        raise ProviderFailure(diagnose(provider, error=error)) from None
    raise ProviderError(f'{provider} model list exceeded the page limit.')


def check_model(provider: str, endpoint: str, model: str, key: str, transport=None) -> ModelAvailability:
    """Check one model against the provider's catalogue.

    The answer is always usable. When the catalogue cannot be read, the
    result says so instead of pretending the model is fine or broken.
    """
    from providers.chat import ProviderError, ProviderFailure

    model = str(model or '').strip()
    if not model:
        return ModelAvailability(
            provider=provider, model='', available=False, known=False,
            detail='No model is selected. Open Advanced settings and choose a model.')

    try:
        models = list_models(provider, endpoint, key, transport=transport)
    except ProviderFailure as error:
        return ModelAvailability(
            provider=provider, model=model, available=False, known=False,
            detail=str(error), diagnosis=error.diagnosis)
    except ProviderError as error:
        return ModelAvailability(
            provider=provider, model=model, available=False, known=False,
            detail=str(error))

    if _normalise(model) in models:
        return ModelAvailability(
            provider=provider, model=model, available=True, known=True,
            detail=f'{model} is listed in the catalogue for this key on {provider}. '
                   'Use the connection test to verify generation.',
            models=models)

    closest = _closest(models, model)
    suggestion = f' A similar model is "{closest}".' if closest else ''
    return ModelAvailability(
        provider=provider, model=model, available=False, known=True,
        detail=(f'{provider} does not serve "{model}" to this key.{suggestion} '
                f'Use the recommended model, or pick one from the provider list.'),
        models=models)


def _common_prefix(left: str, right: str) -> int:
    """How many leading characters two strings share."""
    count = 0
    for first, second in zip(left, right):
        if first != second:
            break
        count += 1
    return count


def _closest(models: tuple[str, ...], model: str) -> str | None:
    """The offered model that shares the most with the requested one."""
    wanted = _normalise(model)
    if not wanted:
        return None
    best = None
    best_score = 0
    for offered in models:
        shared = _common_prefix(wanted, offered)
        if shared > best_score:
            best, best_score = offered, shared
    # A single shared character is not a suggestion.
    return best if best_score >= 4 else None


__all__ = ['ModelAvailability', 'check_model', 'list_models', 'model_list_endpoint']
