"""Streaming rumble/DC rejection without a speech gate or calibration silence."""
import math
import numpy as np


class MicrophoneRumbleFilter:
    """A 70 Hz Butterworth high-pass; preserves quiet speech and adds no buffering."""

    def __init__(self):
        self.clear()

    def clear(self):
        self.rate = None
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0

    def process(self, samples, rate):
        if not len(samples):
            return samples
        if rate < 1000:
            return samples
        if rate != self.rate:
            self.clear()
            self.rate = rate
            omega = 2 * math.pi * 70 / rate
            cosine, alpha = math.cos(omega), math.sin(omega) / math.sqrt(2)
            norm = 1 + alpha
            self.b0 = (1 + cosine) / (2 * norm)
            self.b1 = -(1 + cosine) / norm
            self.a1 = -2 * cosine / norm
            self.a2 = (1 - alpha) / norm
        result = np.empty(len(samples), dtype=np.float64)
        x1, x2, y1, y2 = self.x1, self.x2, self.y1, self.y2
        for index, sample in enumerate(samples):
            value = float(sample)
            output = self.b0 * value + self.b1 * x1 + self.b0 * x2 - self.a1 * y1 - self.a2 * y2
            result[index] = output
            x2, x1, y2, y1 = x1, value, y1, output
        self.x1, self.x2, self.y1, self.y2 = x1, x2, y1, y2
        return np.clip(np.rint(result), -32768, 32767).astype('<i2')
