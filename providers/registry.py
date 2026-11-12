"""Registry of the AI providers JARVIS can talk to.

The registry is the single place that knows which provider exists, where it
lives, how it authenticates and whether it is local. The six cloud providers
already used by the desktop chat flow are taken from `providers.chat` so the
existing behaviour is unchanged; Claude and Ollama are added here because they
need a different request shape or a different trust level.

Local means local: Ollama runs on this machine and is the only provider that
may be used in offline mode. It never carries an API key.
"""
from dataclasses import dataclass

from providers.chat import PROVIDERS as _CLOUD_PROVIDERS


@dataclass(frozen=True)
class ProviderSpec:
    """Everything the router needs to know about one provider."""

    name: str
    endpoint: str
    default_model: str
    #: 'bearer' for the OpenAI compatible shape, 'anthropic' for the native
    #: Anthropic Messages API, 'none' for a local provider without a key.
    auth: str
    local: bool = False
    requires_key: bool = True
    notes: str = ''


_CLAUDE = ProviderSpec(
    name='Claude',
    endpoint='https://api.anthropic.com/v1/messages',
    default_model='claude-sonnet-4-5',
    auth='anthropic',
    notes='Native Anthropic Messages API. Not OpenAI compatible.',
)

_OLLAMA = ProviderSpec(
    name='Ollama',
    endpoint='http://127.0.0.1:11434/v1/chat/completions',
    default_model='llama3.2',
    auth='none',
    local=True,
    requires_key=False,
    notes='Local model. Loopback only, no key, no network egress.',
)

_SPECS = {
    name: ProviderSpec(name=name, endpoint=spec.endpoint, default_model=spec.default_model,
                       auth='bearer')
    for name, spec in _CLOUD_PROVIDERS.items()
}
_SPECS[_CLAUDE.name] = _CLAUDE
_SPECS[_OLLAMA.name] = _OLLAMA


def specs() -> dict[str, ProviderSpec]:
    """Every provider, keyed by its display name."""
    return dict(_SPECS)


def provider_names() -> list[str]:
    """The provider names in a stable order."""
    return list(_SPECS)


def local_provider_names() -> list[str]:
    """Providers that run on this machine."""
    return [name for name, spec in _SPECS.items() if spec.local]


def spec(name: str) -> ProviderSpec:
    """Look up one provider."""
    try:
        return _SPECS[name]
    except KeyError:
        raise KeyError('Unknown provider.') from None


def is_local(name: str) -> bool:
    """True when the provider runs on this machine."""
    return spec(name).local
