"""Voice support for JARVIS AI.

What is implemented and tested here:

- `voice.text_tools` — normalisation and fuzzy scoring, ported from the
  Android client so a transcript is judged the same way on both platforms.
- `voice.wake` — wake phrase matching with the same accepted spellings,
  scoring and thresholds as the Android client.
- `voice.consent` — the microphone permission and the stop control.

What is written but not executed in this environment:

- `voice.windows_tts` — Windows SAPI text to speech. Needs Windows and the
  optional pywin32 package.
- `voice.windows_stt` — Windows offline speech recognition. Needs Windows and
  the optional pythonnet package.

Neither adapter may open the microphone before `voice.consent.VoiceConsent`
has granted permission.
"""
from voice.consent import VoiceConsent, VoiceError
from voice.text_tools import (
    fuzzy_similarity, levenshtein, normalize, similarity, tokens,
)
from voice.wake import (
    ACCEPTANCE_THRESHOLD, DEFAULT_PHRASE, Match, WakePhraseMatcher,
)

__all__ = [
    'ACCEPTANCE_THRESHOLD',
    'DEFAULT_PHRASE',
    'Match',
    'VoiceConsent',
    'VoiceError',
    'WakePhraseMatcher',
    'fuzzy_similarity',
    'levenshtein',
    'normalize',
    'similarity',
    'tokens',
]
