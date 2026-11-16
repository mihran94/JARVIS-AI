"""Fast and Deep model profiles, and which providers actually offer two.

WHAT THIS IS FOR
    JARVIS had two ideas of "a model" in two places. The Quantum Core HUD had
    a Fast and a Deep Gemini model. The desktop application had one model per
    provider. An owner who chose Fast in the HUD and then opened the desktop
    app got a different model, and nothing in the interface said so.

    So the profile idea now lives in one place, and a provider declares
    whether it has two models or one.

WHICH PROVIDERS HAVE TWO
    Only the providers where two real, current model IDs are known are given
    profiles. A provider with one model keeps one model. That is not a gap to
    be filled in later with a guess: inventing a "Deep" model ID that the
    provider does not serve would reproduce exactly the HTTP 404 problem this
    section exists to fix.

    Gemini has both. `gemini-3.5-flash-lite` is the low-latency model and
    `gemini-3.8-flash` is the reasoning model, and both are current. The
    previous pair, `gemini-2.5-flash` and `gemini-2.5-pro`, are deprecated and
    are no longer selectable in AI Studio.

WHAT THIS MODULE WILL NOT DO
    * It never decides which model to use on its own. The owner chooses the
      profile, and the profile chooses the model.
    * It never reaches the network. Whether the model actually exists for the
      owner's key is answered by `providers.models.check_model`.
"""
from __future__ import annotations


#: The profile names, in the order they are offered.
PROFILE_NAMES = ('fast', 'deep')

#: The label the owner sees for each profile.
PROFILE_LABELS = {
    'fast': 'Fast',
    'deep': 'Deep',
}

#: What each profile is for, shown next to the choice.
PROFILE_NOTES = {
    'fast': 'Low latency and low cost. Everyday conversation.',
    'deep': 'Frontier reasoning and long answers.',
}

#: The providers that offer two models, and the model for each profile.
#:
#: A provider that is not listed here has one model and no profile choice.
PROFILE_MODELS = {
    'Gemini': {
        'fast': 'gemini-3.5-flash-lite',
        'deep': 'gemini-3.8-flash',
    },
}


def profiles_for(provider: str) -> dict[str, str]:
    """The profile models for a provider, or an empty mapping."""
    return dict(PROFILE_MODELS.get(provider, {}))


def supports_profiles(provider: str) -> bool:
    """True when the provider offers more than one model."""
    return len(PROFILE_MODELS.get(provider, {})) > 1


def profile_names(provider: str) -> list[str]:
    """The profile names a provider offers, in the standard order."""
    available = PROFILE_MODELS.get(provider, {})
    return [name for name in PROFILE_NAMES if name in available]


def profile_for(provider: str, model: str) -> str | None:
    """The profile that a model ID belongs to, or None when it is not one."""
    wanted = str(model or '').strip().casefold()
    for name, offered in PROFILE_MODELS.get(provider, {}).items():
        if offered.casefold() == wanted:
            return name
    return None


def model_for(provider: str, profile: str, fallback: str = '') -> str:
    """The model a profile means for a provider.

    A provider without profiles keeps its own single model, so the fallback
    is returned unchanged rather than an empty string.
    """
    available = PROFILE_MODELS.get(provider, {})
    if profile in available:
        return available[profile]
    return fallback


def default_profile(provider: str) -> str:
    """The profile a provider starts on."""
    names = profile_names(provider)
    return names[0] if names else ''


def describe(provider: str, profile: str = '', model: str = '') -> str:
    """One line for the interface: provider, profile and model.

    A provider without profiles has no profile to show, so only the provider
    and its model are named.
    """
    available = PROFILE_MODELS.get(provider, {})
    chosen = profile if profile in available else default_profile(provider)
    chosen_model = model or (available.get(chosen, '') if chosen else '')
    if not chosen_model:
        return provider
    if not chosen:
        return f'{provider} · {chosen_model}'
    label = PROFILE_LABELS.get(chosen, chosen.title())
    return f'{provider} · {label} · {chosen_model}'


__all__ = ['PROFILE_LABELS', 'PROFILE_MODELS', 'PROFILE_NAMES', 'PROFILE_NOTES',
           'default_profile', 'describe', 'model_for', 'profile_for', 'profile_names',
           'profiles_for', 'supports_profiles']
