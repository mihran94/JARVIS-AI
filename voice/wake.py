"""Wake phrase matching for the desktop.

This is a faithful port of the Android implementation in
`core/voice/src/main/kotlin/com/jarvisblue/core/voice/WakePhraseMatcher.kt`
(jarvis-blue-android). The accepted spellings, the scoring and the thresholds
are identical, so a transcript is judged the same way on both platforms.

As on Android, the *transcript* is matched rather than an acoustic hotword
model: a third party application cannot run a true always-on hotword engine
on Android without becoming the default assistant. On Windows the platform
does offer an offline recogniser, and `voice/windows_stt.py` uses it.
"""
from dataclasses import dataclass

from voice.text_tools import fuzzy_similarity, normalize

ENGLISH = 'en'
TAMIL = 'ta'
FRENCH = 'fr'

DEFAULT_PHRASE = 'Hey Jarvis Blue'
ACCEPTANCE_THRESHOLD = 0.75

VARIANTS = {
    ENGLISH: [
        'hey jarvis blue',
        'hey jarvis',
        'jarvis blue',
        'jarvis',
        'hey jarvis bleu',
    ],
    TAMIL: [
        'ஹே ஜார்விஸ் புளூ',
        'ஹே ஜார்விஸ்',
        'ஜார்விஸ் புளூ',
        'ஜார்விஸ்',
        'hey jarvis blue',
    ],
    FRENCH: [
        'salut jarvis',
        'hey jarvis blue',
        'jarvis bleu',
        'jarvis',
    ],
}


@dataclass(frozen=True)
class Match:
    """The outcome of matching a transcript against the accepted spellings."""

    matched: bool
    confidence: float
    matched_phrase: str = ''
    language: str = ''

    @property
    def is_wake_call(self) -> bool:
        return self.matched and self.confidence >= ACCEPTANCE_THRESHOLD


class WakePhraseMatcher:
    """Matches the wake phrase inside a speech recognition transcript."""

    def __init__(self, canonical_phrase: str = DEFAULT_PHRASE):
        self.canonical_phrase = canonical_phrase

    def match(self, transcript: str, language: str | None = None) -> Match:
        """Score a transcript against the accepted spellings."""
        normalised = normalize(transcript)
        if not normalised:
            return Match(matched=False, confidence=0.0)
        if language:
            order = [language] + [code for code in VARIANTS if code != language]
        else:
            order = list(VARIANTS)
        best = Match(matched=False, confidence=0.0)
        for code in order:
            for variant in VARIANTS.get(code, []):
                normalised_variant = normalize(variant)
                if not normalised_variant:
                    continue
                contains = normalised_variant in normalised
                score = fuzzy_similarity(normalised, normalised_variant)
                if contains:
                    confidence = 1.0
                elif score >= 0.82:
                    confidence = score
                else:
                    confidence = score * 0.6
                if confidence > best.confidence:
                    best = Match(matched=contains or score >= 0.72, confidence=confidence,
                                 matched_phrase=variant, language=code)
        return best

    def extract_command(self, transcript: str) -> str | None:
        """The instruction that followed the wake phrase, if any."""
        normalised = normalize(transcript)
        for variants in VARIANTS.values():
            for variant in variants:
                normalised_variant = normalize(variant)
                index = normalised.find(normalised_variant)
                if index >= 0:
                    remainder = normalised[index + len(normalised_variant):].strip()
                    return remainder or None
        return None
