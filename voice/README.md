# voice — speech input, output and wake word

Implemented here and covered by local tests:

- `text_tools.py` — normalisation, token overlap, edit distance and the
  fuzzy blend, ported from the Android client so a transcript is scored the
  same way on both platforms.
- `wake.py` — the wake phrase matcher with the same accepted spellings,
  scoring and thresholds as the Android client.
- `consent.py` — the microphone permission and the stop control. The
  microphone is never opened without an explicit grant, and the stop control
  closes it.

Written but not executed in the environment where it was written:

- `windows_tts.py` — Windows SAPI text to speech. Needs Windows and the
  optional pywin32 package.
- `windows_stt.py` — Windows offline speech recognition. Needs Windows and
  the optional pythonnet package.

Neither adapter may open the microphone before `VoiceConsent` has granted
permission, and neither is enabled by default.
