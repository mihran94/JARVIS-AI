"""What a request costs, so the owner can see it without opening a dashboard.

WHAT THIS IS FOR
    The Usage & Health page showed the provider, the model and the token
    counts, and then told the owner to "check your provider dashboard for
    billed costs". That is a to-do, not a number. This module turns the
    token counts JARVIS already records into an estimated cost.

WHY AN ESTIMATE AND NOT A BILL
    JARVIS cannot see the owner's invoice. It knows how many tokens a
    request used, and it can know what a token costs, so it can multiply
    the two. The result is an estimate, and it is labelled as one. Only
    the provider's own dashboard can say what was really charged, because
    only the provider knows about caching, batch discounts, regional
    uplifts and every other rule the list price does not show.

WHY A MODEL WITH NO PRICE IS NOT FREE
    A model that is not in the table has no known price, and an unknown
    price is shown as "price unknown". It is never shown as zero. A
    request that cost money must never look like a request that cost
    nothing. The local provider is the one case where zero is the truth:
    Ollama runs on this machine and is not billed at all.

WHERE THE NUMBERS COME FROM
    Every price below was read from the provider's own pricing page. The
    date is the day they were read, and the source is named, because a
    price that cannot be checked cannot be trusted. Prices change; the
    date tells the owner how old the number is.

    OpenAI      gpt-6-luna                 $0.10 / $0.50
    OpenRouter  openai/gpt-6-luna         $0.10 / $0.50
    MiniMax     MiniMax-M3.1-Flash        $0.15 / $0.60
    DeepSeek    deepseek-flash            $0.30 / $1.20  (the peak rate)
    Groq        openai/gpt-oss-120b       $0.15 / $0.60
    Gemini      gemini-3.5-flash-lite     $0.30 / $2.50
    Gemini      gemini-3.8-flash          $0.75 / $3.75
    Anthropic   claude-sonnet-5-5         $2.00 / $10.00

    DeepSeek bills half the listed rate outside its peak hours, so the
    peak rate is used here: an estimate that is never lower than the
    truth is safer than one that sometimes is.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The day the prices below were read from the providers' own pages.
PRICED_ON = '2026-11-18'

#: Where each price was read from.
SOURCES = {
    'OpenAI': 'https://platform.openai.com/docs/models/gpt-6-luna',
    'OpenRouter': 'https://openrouter.ai/api/v1/chat/completions',
    'MiniMax': 'https://platform.minimax.io/docs/pricing/overview',
    'DeepSeek': 'https://api-docs.deepseek.com/quick_start/pricing',
    'Groq': 'https://console.groq.com/docs/models',
    'Gemini': 'https://ai.google.dev/gemini-api/docs/pricing',
    'Claude': 'https://docs.anthropic.com/en/docs/about-claude/pricing',
}


@dataclass(frozen=True)
class Price:
    """The list price of one model, in US dollars per million tokens."""

    input_per_million: float
    output_per_million: float
    note: str = ''


#: The price of every model JARVIS can be pointed at by default.
PRICES = {
    ('OpenAI', 'gpt-6-luna'): Price(0.10, 0.50),
    ('OpenRouter', 'openai/gpt-6-luna'): Price(0.10, 0.50),
    ('MiniMax', 'MiniMax-M3.1-Flash'): Price(0.15, 0.60),
    ('DeepSeek', 'deepseek-flash'): Price(0.30, 1.20, 'the peak rate; off-peak is half'),
    ('Groq', 'openai/gpt-oss-120b'): Price(0.15, 0.60),
    ('Gemini', 'gemini-3.5-flash-lite'): Price(0.30, 2.50),
    ('Gemini', 'gemini-3.8-flash'): Price(0.75, 3.75, 'through 31 December 2026'),
    ('Claude', 'claude-sonnet-5-5'): Price(2.00, 10.00),
}


def local_provider(provider: str) -> bool:
    """True when this provider runs on this machine and is not billed."""
    return str(provider or '').casefold() == 'ollama'


def price_for(provider: str, model: str) -> Price | None:
    """The price of one provider's model, or None when it is not known.

    A local provider has no price because it has no bill: it costs
    exactly nothing, which is a known number rather than a missing one.
    """
    name = str(provider or '').strip()
    if local_provider(name):
        return Price(0.0, 0.0, 'local model, no bill')
    if not name:
        return None
    found = PRICES.get((name, str(model or '').strip()))
    if found is not None:
        return found
    # A provider that serves a named model of another provider is billed
    # at that model's price.
    bare = str(model or '').strip().split('/')[-1]
    for (other, other_model), price in PRICES.items():
        if other != name:
            continue
        if other_model.casefold() == bare.casefold():
            return price
    return None


def estimate(provider: str, model: str, prompt_tokens=None, completion_tokens=None) -> float | None:
    """The estimated cost of one request in US dollars.

    Returns None when the price of the model is not known, so the caller
    can say "price unknown" instead of inventing a number. A request with
    no token counts costs nothing that can be measured, so it also
    returns None.
    """
    price = price_for(provider, model)
    if price is None:
        return None
    if prompt_tokens is None and completion_tokens is None:
        return None
    prompt = max(0, int(prompt_tokens or 0))
    completion = max(0, int(completion_tokens or 0))
    return (prompt * price.input_per_million + completion * price.output_per_million) / 1_000_000


def format_cost(value: float | None) -> str:
    """The cost as the owner reads it.

    A cost under a cent is still shown, because "less than a cent" is
    information; a cost that is not known is shown as unknown.
    """
    if value is None:
        return 'price unknown'
    if value == 0:
        return '$0.00'
    if value < 0.01:
        return '< $0.01'
    return f'${value:.2f}'


def describe(provider: str, model: str) -> str:
    """One line about what a model costs, for the provider page."""
    price = price_for(provider, model)
    if price is None:
        return (f'{provider} / {model}: price unknown, check the provider dashboard.')
    if price.input_per_million == 0 and price.output_per_million == 0:
        return f'{provider} / {model}: local model, no bill.'
    note = f' ({price.note})' if price.note else ''
    return (f'{provider} / {model}: ${price.input_per_million:.2f} in, '
            f'${price.output_per_million:.2f} out per 1M tokens{note}. '
            f'Read on {PRICED_ON}.')
