"""Local-only speech echo suppression for JARVIS TTS.

This guard is advisory, never opens the mic and never grants permissions.
It only rejects a recent transcript that closely repeats JARVIS's own
spoken reply. It does not make JARVIS a full-duplex barge-in engine.
"""
from __future__ import annotations

import re
import time


def _normalize(text):
    return ' '.join(re.findall(r'[^\W_]+', str(text or '').casefold()))


class EchoGuard:
    def __init__(self, *, window_seconds=2.5, clock=None):
        self.window_seconds = window_seconds
        self.clock = clock or time.monotonic
        self.last_text = ''
        self.last_time = float('-inf')

    def record(self, text):
        self.last_text = _normalize(text)[:1200]
        self.last_time = self.clock()

    def is_echo(self, transcript):
        candidate = _normalize(transcript)
        if not candidate or len(candidate) < 16:
            return False
        if not self.last_text or self.clock() - self.last_time > self.window_seconds:
            return False
        if candidate == self.last_text:
            return True
        return len(candidate) >= 22 and candidate in self.last_text

    def reset(self):
        self.last_text = ''
        self.last_time = float('-inf')
