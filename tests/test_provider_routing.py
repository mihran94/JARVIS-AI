"""Which provider answers the owner, and which one writes code.

The rules are simple and they are checked here without a network, a key or a
window:

* Gemini answers the owner by default, and the owner may choose another
  provider for their own conversations.
* MiniMax and Codex may write code, and nothing else may.
* The coding provider is MiniMax until the owner chooses Codex.
* When the coding provider cannot do the work, the other one is only used
  after the owner approves it.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from core.store import Store
from providers import routing


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'history.sqlite3')


def test_gemini_answers_the_owner_by_default(store):
    assert routing.person_provider(store) == 'Gemini'


def test_the_owner_can_choose_another_person_facing_provider(store):
    routing.set_person_provider(store, 'OpenAI')
    assert routing.person_provider(store) == 'OpenAI'
    # The coding provider is not affected by that choice.
    assert routing.coding_provider(store) == 'MiniMax'


def test_an_unknown_person_facing_provider_is_refused(store):
    with pytest.raises(ValueError):
        routing.set_person_provider(store, 'NotAProvider')


def test_minimax_writes_code_until_the_owner_chooses_otherwise(store):
    assert routing.coding_provider(store) == 'MiniMax'
    routing.set_coding_provider(store, 'Codex')
    assert routing.coding_provider(store) == 'Codex'


def test_the_configured_coding_providers_may_write_code(store):
    for provider in ('MiniMax', 'Codex', 'OpenAI'):
        assert routing.is_coding_provider(provider)
        assert routing.require_coding_provider(provider) == provider
    for provider in ('Gemini', 'Claude', 'Groq', 'DeepSeek', 'OpenRouter', 'Ollama'):
        assert not routing.is_coding_provider(provider)
        with pytest.raises(routing.CodingRouteRefused):
            routing.require_coding_provider(provider)


def test_another_provider_cannot_be_chosen_for_code(store):
    with pytest.raises(routing.CodingRouteRefused):
        routing.set_coding_provider(store, 'Gemini')
    assert routing.coding_provider(store) == 'MiniMax'


def test_the_other_coding_provider_is_the_one_to_ask_for():
    assert routing.other_coding_provider('MiniMax') == 'Codex'
    assert routing.other_coding_provider('Codex') == 'MiniMax'


def test_the_routing_is_described_for_the_interface(store):
    described = routing.describe(store)
    assert described['person'] == 'Gemini'
    assert described['coding'] == 'MiniMax'
    assert described['coding_options'] == ['MiniMax', 'Codex', 'OpenAI']


def test_the_application_offers_only_the_coding_providers(tmp_path, monkeypatch):
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        assert [window.coding_provider.itemText(index)
                for index in range(window.coding_provider.count())] == ['MiniMax', 'Codex', 'OpenAI']
        assert window.selected_coding_provider() == 'MiniMax'
        # The chat provider cannot become the coding provider.
        window.chat_provider.setCurrentText('Gemini')
        assert window.selected_coding_provider() == 'MiniMax'
        window.coding_provider.setCurrentText('Codex')
        assert window.selected_coding_provider() == 'Codex'
        assert routing.coding_provider(window.store) == 'Codex'
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
