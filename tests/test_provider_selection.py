"""Offline tests for the unified provider selection policy."""
import pytest

from providers.selection import NoProviderAvailable, Provider, choose_provider


@pytest.fixture
def providers():
    return (
        Provider('openai', configured=True, healthy=False),
        Provider('gemini', configured=True, healthy=True),
        Provider('ollama', configured=True, healthy=True, local=True),
    )


def test_no_implicit_fallback(providers):
    with pytest.raises(NoProviderAvailable):
        choose_provider(providers, 'openai')


def test_explicit_fallback(providers):
    assert choose_provider(providers, 'openai', allow_fallback=True).name == 'gemini'


def test_offline_selects_local(providers):
    chosen = choose_provider(providers, 'openai', allow_fallback=True, offline_only=True)
    assert chosen.name == 'ollama'


def test_offline_rejects_remote(providers):
    with pytest.raises(NoProviderAvailable):
        choose_provider(providers, 'gemini', offline_only=True)


def test_unknown_preference_rejected(providers):
    with pytest.raises(ValueError):
        choose_provider(providers, 'nonexistent', allow_fallback=True)


def test_duplicate_names_rejected():
    with pytest.raises(ValueError):
        choose_provider((Provider('x', True, True), Provider('x', True, True)), 'x')


def test_unconfigured_provider_rejected():
    with pytest.raises(NoProviderAvailable):
        choose_provider((Provider('ollama', False, True, local=True),), 'ollama')
