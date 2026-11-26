"""Microphone consent and the voice stop control.

The microphone is never opened without an explicit grant, the grant is shown
to the owner, and the emergency stop closes it again. The control is pure
state, so it can be tested without a microphone and without Windows.
"""
from threading import RLock

from voice.errors import VoiceError


class VoiceConsent:
    """Holds the microphone permission and the stop latch.

    `granted` means the owner allowed the microphone. `listening` means the
    microphone may be open right now. `stop()` closes it and invalidates any
    outstanding permission until `resume()` is called, exactly like the
    emergency stop in `security.policy.Policy`.
    """

    def __init__(self):
        self._lock = RLock()
        self._granted = False
        self._stopped = False
        self._muted = False
        self._listener = None

    # ------------------------------------------------------------ properties

    @property
    def granted(self) -> bool:
        with self._lock:
            return self._granted

    @property
    def stopped(self) -> bool:
        with self._lock:
            return self._stopped

    @property
    def muted(self) -> bool:
        with self._lock:
            return self._muted

    def set_muted(self, muted: bool) -> None:
        """Block input without granting or revoking owner consent."""
        with self._lock:
            self._muted = muted

    @property
    def listening(self) -> bool:
        """True only when the microphone may be open."""
        with self._lock:
            return self._granted and not self._stopped and not self._muted

    @property
    def listener(self) -> str:
        """What the owner was told about the microphone state."""
        with self._lock:
            if self._stopped:
                return 'The microphone is closed by the stop control.'
            if self._muted:
                return 'The microphone is muted for this session.'
            if not self._granted:
                return 'The microphone has not been allowed.'
            return 'The microphone is allowed for the voice feature.'

    # --------------------------------------------------------------- actions

    def grant(self) -> None:
        """Allow the microphone. This is the only way to open it."""
        with self._lock:
            if self._stopped:
                raise VoiceError('Resume the voice feature before allowing the microphone.')
            self._granted = True

    def revoke(self) -> None:
        """Withdraw the permission and close the microphone."""
        with self._lock:
            self._granted = False

    def stop(self) -> None:
        """Close the microphone. The permission is not restored by resuming."""
        with self._lock:
            self._stopped = True
            self._granted = False

    def resume(self) -> None:
        """Allow the microphone to be opened again. The owner must grant it."""
        with self._lock:
            self._stopped = False
            self._granted = False

    def require_listening(self) -> None:
        """Raise unless the microphone may be used right now."""
        with self._lock:
            if self._stopped:
                raise VoiceError('The voice feature is stopped.')
            if self._muted:
                raise VoiceError('Unmute the microphone before listening.')
            if not self._granted:
                raise VoiceError('Allow the microphone before using voice.')
