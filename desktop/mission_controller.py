"""The wiring between the mission console and the running JARVIS.

WHAT THIS IS
    The console is a view; this is the controller. It builds the tool
    catalogue from the services the window already has, builds the
    planner from the provider the owner chose, starts the mission in a
    worker thread, and moves the steps from the worker to the console.

WHAT THIS IS NOT
    * It does not keep a key of its own. The key is taken from the
      window for the length of one mission and cleared when the mission
      ends.
    * It does not decide what the model may do. The catalogue and the
      runtime do that.
    * It does not fall back to another provider. The owner chose one,
      and the mission uses that one or it does not run.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.mission import AgentRuntime, MissionEvent, MAX_STEPS
from core.mission_tools import build_registry
from desktop.mission_panel import MissionWorker
from security.policy import Stopped


class ApprovalBridge(QObject):
    """Carries the owner's approval from the worker thread to the window.

    The mission runs in a worker thread and the approval dialog belongs
    to the interface thread. A queued signal carries the question over,
    and a second signal carries the answer back, so the worker can wait
    for it without touching the interface from the wrong thread.
    """

    asked = Signal(object)
    answered = Signal(bool)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.asked.connect(self.ask)

    @Slot(object)
    def ask(self, action):
        """Ask the owner, and report the answer."""
        try:
            answer = bool(self.window.confirm(action))
        except Exception:
            answer = False
        self.answered.emit(answer)


class MissionController(QObject):
    """Starts, watches and stops missions for the console."""

    def __init__(self, window, panel):
        super().__init__(window)
        self.window = window
        self.panel = panel
        self.worker = None
        self.max_steps = MAX_STEPS
        self._steps = 0
        self._key = ''
        self._from_chat = False
        self.bridge = ApprovalBridge(window)
        panel.run_requested.connect(self.start)
        panel.cancel_requested.connect(self.cancel)

    # ------------------------------------------------------------------

    def start(self, goal: str, *, from_chat: bool = False):
        """Start one mission with the goal the owner typed.

        `from_chat` means the goal came from the conversation, so the
        answer is written back into that conversation when the mission
        finishes. The steps are on the Mission Control page either way.
        """
        window = self.window
        if self.worker is not None and self.worker.isRunning():
            # The mission that is running keeps its own state; the console
            # only says that this one was refused.
            self.panel.append_event(
                MissionEvent('error', 'A mission is already running',
                             'Wait for it to finish, or cancel it first.'))
            return
        try:
            provider = window.chat_provider.currentText()
            model = window.selected_model(provider)
            self._key = window.get_key(provider)
            ticket = window.policy.ticket()
        except Exception as error:
            self._key = ''
            self.panel.set_running(False)
            self.panel.set_status('failed')
            self.panel.append_event(MissionEvent('error', 'The mission could not start',
                                                 str(error)))
            return

        from automation.windows import EDITOR_EXECUTABLES

        editor_paths = {name: window.store.get('editor_path:' + name, '') for name in EDITOR_EXECUTABLES}
        registry = build_registry(root=window.root, memory=window.memory_service, editor_paths=editor_paths)
        self.max_steps, budget_seconds = self.panel.run_limit.currentData()
        runtime = AgentRuntime(
            registry,
            window.gateway,
            self._planner(provider, model, ticket),
            max_steps=self.max_steps,
            budget_seconds=budget_seconds,
            on_event=self.on_event,
            check=lambda: window.policy.check(ticket),
        )
        worker = MissionWorker(runtime, goal, confirm=self._confirm, parent=self)
        worker.event.connect(self.on_event)
        worker.result.connect(self.on_result)
        worker.failed.connect(self.on_failed)
        self.worker = worker
        self._steps = 0
        self._from_chat = from_chat
        self.panel.max_steps = self.max_steps
        self.panel.set_goal(goal)
        self.panel.set_running(True)
        self.panel.set_counter(0, self.max_steps)
        worker.start()

    def cancel(self):
        """Ask the running mission to stop at the next step."""
        if self.worker is not None:
            self.worker.cancel()

    # ------------------------------------------------------------------

    def _planner(self, provider, model, ticket):
        """The model call, as the runtime needs it.

        The provider is the one the owner chose in the chat, the model is
        the one that provider is set to, and there is no fallback: if the
        provider fails, the mission fails and says so.
        """
        window = self.window

        def planner(messages):
            def check():
                window.policy.check(ticket)
                worker = self.worker
                if worker is not None and worker.isInterruptionRequested():
                    raise Stopped('Mission cancelled by the owner.')

            return window.router.stream(window.router.spec(provider), model, self._key,
                                        messages, check, lambda _chunk: None)

        return planner

    def _confirm(self, action):
        """Ask the owner for approval, on the interface thread.

        The mission runs in a worker thread, and a modal dialog has to
        belong to the thread that owns the window. The question is
        handed to that thread and the worker waits for the answer. A
        cancelled mission does not wait for ever.
        """
        window = self.window
        if QThread.currentThread() is window.thread():
            return bool(window.confirm(action))
        answer = {}
        done = threading.Event()

        def on_answer(value):
            answer['value'] = bool(value)
            done.set()

        self.bridge.answered.connect(on_answer)
        try:
            self.bridge.asked.emit(action)
            while not done.wait(0.2):
                worker = self.worker
                if worker is not None and worker.isInterruptionRequested():
                    return False
            return answer.get('value', False)
        finally:
            try:
                self.bridge.answered.disconnect(on_answer)
            except (RuntimeError, TypeError):
                pass

    # ------------------------------------------------------------------

    def on_event(self, event):
        """Move one step of the mission to the console."""
        self.panel.append_event(event)
        if event.kind == 'tool':
            self._steps += 1
        if event.step:
            # The counter is the mission's step of its budget, and it is
            # the same number before and after the mission.
            self.panel.set_counter(event.step, self.max_steps)
        if event.kind == 'approval':
            # The mission is waiting for the owner, and the pill says so.
            self.panel.set_status('approval')
        elif event.kind in ('tool', 'result') and self.panel.current_status() == 'approval':
            self.panel.set_status('running')

    def on_result(self, mission):
        """The mission finished."""
        self._key = ''
        self.panel.set_running(False)
        self.panel.show_result(mission)
        if self._from_chat:
            self._from_chat = False
            self.window.mission_answered(mission)
        self.window.mission_finished()

    def on_failed(self, message):
        """The mission could not run at all."""
        self._key = ''
        self.panel.set_running(False)
        self.panel.set_status('failed')
        self.panel.append_event(MissionEvent('error', 'Mission failed', message))
        if self._from_chat:
            self._from_chat = False
            self.window.mission_answered(None, message)
        self.window.mission_finished()


__all__ = ['MissionController']
