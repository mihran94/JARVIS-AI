"""Suppress strong, recent playback copies without gating the user's mic."""
from time import monotonic

import numpy as np


class PlaybackEchoFilter:
    RATE = 2000

    def __init__(self):
        self.clear()

    def clear(self):
        self.reference = np.empty(0, dtype=np.float64)
        self.updated = 0.0

    @classmethod
    def downsample(cls, samples, rate):
        count = int(len(samples) * cls.RATE / rate)
        if not count:
            return np.empty(0, dtype=np.float64)
        return np.interp(np.arange(count) * rate / cls.RATE,
                         np.arange(len(samples)), samples)

    def played(self, samples, rate):
        self.reference = np.concatenate((self.reference, self.downsample(samples, rate)))[-3000:]
        self.updated = monotonic()

    def filter(self, samples, rate):
        """Remove only a highly correlated speaker copy; retain other speech.

        This is conservative playback-copy suppression, not a replacement for
        the microphone/driver's acoustic echo cancellation.
        """
        mic = self.downsample(samples, rate)
        if len(mic) < 32 or len(self.reference) < len(mic) or monotonic() - self.updated > 1.0:
            return samples
        mic = mic - mic.mean()
        energy = float(mic @ mic)
        if energy < len(mic) * 16:
            return samples
        reference = self.reference
        count = len(mic)
        sums = np.concatenate(([0.0], np.cumsum(reference)))
        squares = np.concatenate(([0.0], np.cumsum(reference * reference)))
        means = (sums[count:] - sums[:-count]) / count
        energies = np.maximum(squares[count:] - squares[:-count] - count * means * means, 1.0)
        correlation = np.correlate(reference, mic, mode='valid') / np.sqrt(energies * energy)
        best = int(np.argmax(np.abs(correlation)))
        if abs(correlation[best]) < 0.92:
            return samples
        # Near-identical playback is echo, not a new request. Mixed or unrelated
        # speech is deliberately passed through to Gemini's activity detector.
        return np.zeros_like(samples)
