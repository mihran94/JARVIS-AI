"""What a request costs, and what JARVIS says when it does not know."""
import pytest

from providers import pricing


def test_a_known_model_is_priced_from_its_list_price():
    price = pricing.price_for('OpenAI', 'gpt-6-luna')
    assert price is not None
    assert price.input_per_million == 0.10
    assert price.output_per_million == 0.50


def test_the_estimate_multiplies_the_tokens_by_the_price():
    # 1000 input tokens at $0.10 per million is $0.0001.
    cost = pricing.estimate('OpenAI', 'gpt-6-luna', 1000, 0)
    assert cost == pytest.approx(0.0001)
    # 1000 output tokens at $0.50 per million is $0.0005.
    assert pricing.estimate('OpenAI', 'gpt-6-luna', 0, 1000) == pytest.approx(0.0005)
    assert pricing.estimate('OpenAI', 'gpt-6-luna', 1000, 1000) == pytest.approx(0.0006)


def test_a_local_model_is_free_and_says_so():
    """Zero is the truth for a local model, not a missing price."""
    price = pricing.price_for('Ollama', 'qwen3:8b')
    assert price is not None
    assert price.input_per_million == 0
    assert price.output_per_million == 0
    assert pricing.estimate('Ollama', 'qwen3:8b', 100000, 100000) == 0
    assert pricing.format_cost(0) == '$0.00'


def test_an_unknown_model_has_no_price_and_is_never_shown_as_free():
    """A model with no price must not look like a model that costs nothing."""
    cost = pricing.estimate('SomeProvider', 'some-model', 1000, 1000)
    assert cost is None
    assert pricing.format_cost(cost) == 'price unknown'
    assert pricing.price_for('SomeProvider', 'some-model') is None


def test_a_missing_token_count_has_no_estimate():
    assert pricing.estimate('OpenAI', 'gpt-6-luna', None, None) is None


def test_every_default_model_of_every_provider_is_priced():
    """A provider JARVIS offers by default must have a price."""
    from providers.profiles import PROFILE_MODELS
    from providers.registry import specs

    for name, spec in specs().items():
        if spec.local:
            continue
        models = [spec.default_model] + list(PROFILE_MODELS.get(name, {}).values())
        for model in models:
            assert pricing.price_for(name, model) is not None, f'{name} / {model}'


def test_a_model_served_by_another_provider_keeps_its_own_price():
    """OpenRouter serves openai/gpt-6-luna at the model's own price."""
    assert pricing.price_for('OpenRouter', 'openai/gpt-6-luna') == \
        pricing.price_for('OpenAI', 'gpt-6-luna')


def test_the_prices_carry_the_day_they_were_read_and_where_from():
    """A price that cannot be checked cannot be trusted."""
    assert pricing.PRICED_ON
    for provider in ('OpenAI', 'MiniMax', 'DeepSeek', 'Groq', 'Gemini', 'Claude'):
        assert provider in pricing.SOURCES
        assert pricing.SOURCES[provider].startswith('https://')


def test_a_small_cost_is_still_shown():
    """Less than a cent is information, not nothing."""
    assert pricing.format_cost(0.0001) == '< $0.01'
    assert pricing.format_cost(1.25) == '$1.25'


def test_the_provider_page_shows_the_price_of_the_chosen_model(tmp_path):
    """The owner sees the price before the request is sent, not after."""
    from PySide6.QtWidgets import QApplication

    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        window.provider.setCurrentText('OpenAI')
        app.processEvents()
        assert 'per 1M tokens' in window.price_note.text()
        window.model.setText('some-model-nobody-has-priced')
        app.processEvents()
        assert 'price unknown' in window.price_note.text()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_the_usage_page_shows_a_cost_and_says_when_it_does_not_know(tmp_path):
    """The page has to carry a cost column and a summary."""
    from PySide6.QtWidgets import QApplication

    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        window.store.record_usage(
            'task-1', 'OpenAI', 'gpt-6-luna', 'completed',
            {'duration_ms': 120, 'prompt_tokens': 1000, 'completion_tokens': 1000,
             'total_tokens': 2000})
        window.store.record_usage(
            'task-2', 'SomeProvider', 'some-model', 'completed',
            {'duration_ms': 90, 'prompt_tokens': 100, 'completion_tokens': 100,
             'total_tokens': 200})
        window.refresh_history()
        headers = [window.usage_table.horizontalHeaderItem(index).text()
                   for index in range(window.usage_table.columnCount())]
        assert 'Est. cost' in headers
        assert window.usage_table.rowCount() == 2
        costs = [window.usage_table.item(row, headers.index('Est. cost')).text()
                 for row in range(2)]
        assert 'price unknown' in costs
        assert any(cost not in ('price unknown', '$0.00') for cost in costs)
        assert 'Estimated total' in window.usage_cost_summary.text()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
