"""The exceptions used by the voice layer.

They live in one place so that an adapter and the caller refer to the same
class.
"""


class VoiceError(RuntimeError):
    """The voice layer refused an operation."""


class VoiceUnavailable(VoiceError):
    """Speech is not usable on this machine."""
