"""The coding mission, run away from the interface thread.

WHAT THIS IS
    The worker that lets the owner keep using JARVIS while a coding
    mission works. It reports every step as it happens, so the console
    shows the mission while it runs rather than after it finishes.

WHAT THIS IS NOT
    * It does not decide anything. The mission and the repair loop do.
    * It does not touch the provider without one: the key is taken from
      the window and cleared when the mission ends.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from security.policy import Stopped


class CodingMissionWorker(QThread):
    """Runs one coding mission and reports its steps."""

    event = Signal(object)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, mission, policy, ticket, parent=None):
        super().__init__(parent)
        self.mission = mission
        self.policy = policy
        self.ticket = ticket
        self._cancelled = False

    def cancel(self):
        """Ask the mission to stop at the next step."""
        self._cancelled = True
        self.requestInterruption()

    def check(self):
        """The emergency stop and the owner's cancellation."""
        self.policy.check(self.ticket)
        if self._cancelled or self.isInterruptionRequested():
            raise Stopped('The coding mission was cancelled.')

    def run(self):
        self.mission.cancel = self.check
        self.mission.on_event = self.event.emit
        try:
            result = self.mission.run()
        except Stopped:
            self.failed.emit('The coding mission was cancelled.')
            return
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.result.emit(result)


__all__ = ['CodingMissionWorker']
