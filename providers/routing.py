"""Which provider is allowed to do which kind of work.

WHAT THIS IS FOR
    JARVIS talks to the owner and JARVIS edits code. Those are different
    jobs, and they get different providers.

    * Person-facing work — the chat, the spoken replies, the daily tasks and
      the explanation of a proposed update — goes to Gemini by default. The
      owner can still choose another provider for that work, because some
      people want a different model for their own conversations.

    * Source-code work — editing, fixing and preparing a change to a
      repository — goes to OpenAI, MiniMax or Codex. No other
      provider may be used to write code, whatever the chat provider is set
      to. That is a rule about the work, not about the preference.

WHY IT IS A SEPARATE MODULE
    The rule has to hold in every place that can start a request, including
    the places that are not in the chat window. Keeping it here means there
    is one list to change and one function to call, and a test can check the
    rule without a network, a key or a window.
"""
from __future__ import annotations

from providers.registry import provider_names

#: The provider used for the owner's own conversations unless they choose one.
PERSON_FACING_DEFAULT = 'Gemini'

#: The only providers allowed to read, write or fix source code.
CODING_PROVIDERS = ('MiniMax', 'Codex', 'OpenAI')

#: The coding provider used until the owner chooses another one.
CODING_DEFAULT = 'MiniMax'

PERSON_KEY = 'chat_provider'
CODING_KEY = 'coding_provider'


class CodingRouteRefused(ValueError):
    """Raised when a request to edit code is routed to a provider that may not."""


def person_provider(store) -> str:
    """The provider that answers the owner."""
    saved = str(store.get(PERSON_KEY) or '').strip()
    if saved in provider_names():
        return saved
    return PERSON_FACING_DEFAULT


def set_person_provider(store, name: str) -> str:
    """Remember the provider for the owner's conversations."""
    if name not in provider_names():
        raise ValueError('Unknown provider.')
    store.set(PERSON_KEY, name)
    return name


def coding_provider(store) -> str:
    """The provider that edits code."""
    saved = str(store.get(CODING_KEY) or '').strip()
    if saved in CODING_PROVIDERS:
        return saved
    return CODING_DEFAULT


def set_coding_provider(store, name: str) -> str:
    """Remember the provider that edits code.

    OpenAI, MiniMax and Codex may be chosen. A caller that offers a provider
    that may not write code is refused here rather than at the call site.
    """
    if name not in CODING_PROVIDERS:
        raise CodingRouteRefused(
            'Only ' + ' and '.join(CODING_PROVIDERS) + ' may edit source code.')
    store.set(CODING_KEY, name)
    return name


def coding_provider_names() -> list[str]:
    """The providers the owner may choose for code work."""
    return list(CODING_PROVIDERS)


def is_coding_provider(name: str) -> bool:
    """True when this provider may edit source code."""
    return name in CODING_PROVIDERS


def other_coding_provider(name: str) -> str:
    """The other coding provider, used when the owner approves a switch."""
    for candidate in CODING_PROVIDERS:
        if candidate != name:
            return candidate
    raise ValueError('No other coding provider is available.')


def require_coding_provider(name: str) -> str:
    """Check that a provider may edit code, and return it."""
    if not is_coding_provider(name):
        raise CodingRouteRefused(
            f'{name} may not edit source code. Use ' + ' or '.join(CODING_PROVIDERS) + '.')
    return name


def describe(store) -> dict:
    """What the interface shows about the routing."""
    return {
        'person': person_provider(store),
        'person_default': PERSON_FACING_DEFAULT,
        'coding': coding_provider(store),
        'coding_options': coding_provider_names(),
        'coding_default': CODING_DEFAULT,
    }
