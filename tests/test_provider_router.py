"""Offline tests for the provider registry and the router."""
import pytest

from providers.registry import ProviderSpec, is_local, local_provider_names, provider_names, specs
from providers.router import ProviderRouter
from providers.selection import NoProviderAvailable

CONFIGURED = ('OpenAI', 'Gemini', 'Claude', 'Ollama')


def test_the_registry_covers_the_agreed_provider_set():
    names = set(provider_names())
    assert names == {'OpenAI', 'Gemini', 'Claude', 'MiniMax', 'DeepSeek', 'Groq',
                     'OpenRouter', 'Ollama'}


def test_only_ollama_is_local():
    assert local_provider_names() == ['Ollama']
    assert is_local('Ollama') is True
    assert is_local('OpenAI') is False


def test_the_local_provider_needs_no_key_and_uses_loopback():
    spec = specs()['Ollama']
    assert spec.requires_key is False
    assert spec.endpoint.startswith('http://127.0.0.1')


def test_claude_uses_the_native_anthropic_endpoint():
    spec = specs()['Claude']
    assert spec.auth == 'anthropic'
    assert spec.endpoint == 'https://api.anthropic.com/v1/messages'


def test_the_router_selects_the_preferred_provider():
    router = ProviderRouter()
    chosen = router.select('OpenAI', configured=CONFIGURED)
    assert chosen.name == 'OpenAI'


def test_the_router_has_no_implicit_fallback():
    router = ProviderRouter(health={'OpenAI': False})
    with pytest.raises(NoProviderAvailable):
        router.select('OpenAI', configured=CONFIGURED)


def test_the_router_falls_back_only_with_explicit_consent():
    router = ProviderRouter(health={'OpenAI': False})
    chosen = router.select('OpenAI', configured=CONFIGURED, allow_fallback=True)
    assert chosen.name == 'Gemini'


def test_offline_mode_never_selects_a_paid_provider():
    router = ProviderRouter()
    chosen = router.select('OpenAI', configured=CONFIGURED, allow_fallback=True,
                           offline_only=True)
    assert chosen.name == 'Ollama'


def test_offline_mode_reports_when_no_local_provider_exists():
    router = ProviderRouter(registry={
        'OpenAI': ProviderSpec('OpenAI', 'https://api.openai.com/v1/chat/completions',
                               'gpt-4.1-mini', 'bearer'),
    })
    with pytest.raises(NoProviderAvailable):
        router.select('OpenAI', configured=('OpenAI',), offline_only=True)


def test_an_unconfigured_provider_is_not_selected():
    router = ProviderRouter()
    with pytest.raises(NoProviderAvailable):
        router.select('Claude', configured=('OpenAI',))


def test_an_unknown_provider_name_is_refused():
    router = ProviderRouter()
    with pytest.raises(ValueError):
        router.select('Nonexistent', configured=CONFIGURED)
