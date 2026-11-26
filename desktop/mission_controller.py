"""The wiring between the mission console and the running JARVIS.

WHAT THIS IS
    The console is a view; this is the controller. It builds the tool
    catalogue from the services the window already has, builds the
    planner from the engines the window already has, starts the mission
    in a worker thread, and moves the steps from the worker to the
    console.

    The mission is local first. The on-device model answers a step
    whenever it can. When the owner has turned on "Use Gemini
    automatically when needed" and the local model could not do that
    step, exactly that step is sent to Gemini, and the console says so.

WHAT THIS IS NOT
    * It does not keep a key of its own. The key is taken from the
      window for the length of one mission and cleared when the mission
      ends.
    * It does not decide what the model may do. The catalogue and the
      runtime do that.
    * It does not approve anything itself. Every action that changes
      something goes through the same gateway as every other action.
"""
from __future__ import annotations

import json
import threading
import uuid

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.engines import EngineUnavailable
from core.mission import AgentRuntime, MissionError, MissionEvent, MAX_STEPS, parse_decision
from core.mission_tools import build_registry
from desktop.mission_panel import MissionWorker
from security.policy import Action, Stopped


class ApprovalBridge(QObject):
    """Carries the owner's approval from the worker thread to the window.

    The mission runs in a worker thread and the proposal belongs to the
    interface thread. A queued signal carries the question over, and a
    second signal carries the answer back, so the worker can wait for it
    without touching the interface from the wrong thread.
    """

    asked = Signal(str, object, object)
    answered = Signal(str, object)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.asked.connect(self.ask)

    @Slot(str, object, object)
    def ask(self, ident, action, editable):
        """Show the proposed action and let the owner answer it."""
        try:
            self.window.propose_action(ident, action, editable)
        except Exception:
            # The proposal cannot be shown. The mission is told nothing
            # was approved, rather than running the action unseen.
            self.answered.emit(ident, False)


class MissionController(QObject):
    """Starts, watches and stops missions for the console."""

    #: Which engine answered a step, and why.
    engine_used = Signal(object)

    #: The step of the mission that is running now, and its budget.
    step_changed = Signal(int, int)

    def __init__(self, window, panel):
        super().__init__(window)
        self.window = window
        self.panel = panel
        self.worker = None
        self.max_steps = MAX_STEPS
        self._steps = 0
        self._key = ''
        self._from_chat = False
        self._step = 0
        self._waiting = {}
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
        registry = build_registry(root=window.root, memory=window.memory_service, editor_paths=editor_paths,
                                  input_allowed=lambda kind: bool(window.store.get('input:' + kind, True)))
        self.max_steps, budget_seconds = self.panel.run_limit.currentData()
        window.refresh_engine_settings()
        window.engines.validate = lambda text: parse_decision(text)[0] is not None
        window.engines.on_record = self.on_engine_record
        window.engines.approve_share = self.approve_share
        runtime = AgentRuntime(
            registry,
            window.gateway,
            self._planner(provider, model, ticket),
            max_steps=self.max_steps,
            budget_seconds=budget_seconds,
            on_event=self.on_event,
            check=lambda: window.policy.check(ticket),
            compact_tools=True,
        )
        worker = MissionWorker(runtime, goal, confirm=self._confirm, parent=self)
        worker.event.connect(self.on_event)
        worker.result.connect(self.on_result)
        worker.failed.connect(self.on_failed)
        self.worker = worker
        self._steps = 0
        self._step = 0
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

        The on-device model answers the step. Gemini answers it only when
        the owner allowed the automatic fallback and the local model
        could not do that step. When Gemini is not available either, the
        step is reported as blocked and the mission carries on with the
        steps the local model can do.
        """
        window = self.window

        def planner(messages):
            def check():
                window.policy.check(ticket)
                worker = self.worker
                if worker is not None and worker.isInterruptionRequested():
                    raise Stopped('Mission cancelled by the owner.')

            router = window.engines
            router.check = check
            try:
                text, _record = router.plan_step(messages, step=self._step)
            except EngineUnavailable as error:
                if not getattr(error, 'blocked', False):
                    raise MissionError(str(error)) from None
                # The step cannot be done. The mission says so and moves
                # on to the work that can be done.
                self.panel.append_event(MissionEvent(
                    'error', 'This step is blocked', str(error), self._step))
                return json.dumps({
                    'action': 'skip',
                    'reason': str(error),
                    'thought': 'This step cannot be done here.',
                })
            return text

        return planner

    def approve_share(self, kinds, note: str) -> bool:
        """Ask the owner, on the interface thread, before sharing.

        The question goes through the same approval gateway as every
        other action, so a refusal is recorded in the same place as any
        other refusal.
        """
        action = Action('share_with_gemini', note)
        try:
            return bool(self._confirm(action))
        except Exception:
            return False

    # ------------------------------------------------------------------

    def _confirm(self, action):
        """Ask the owner for approval, on the interface thread.

        The mission runs in a worker thread, and a proposal belongs to
        the thread that owns the window. The question is handed to that
        thread and the worker waits for the answer. A cancelled mission
        does not wait for ever.

        The answer may be `True`, `False`, or the arguments the owner
        changed. An answer with arguments means the owner edited the
        action and wants it run that way.
        """
        window = self.window
        if getattr(window, 'desktop_control_allows', lambda _action: False)(action):
            return True
        if QThread.currentThread() is window.thread():
            return bool(window.confirm(action))
        ident = uuid.uuid4().hex[:12]
        answer = {}
        done = threading.Event()

        def on_answer(seen, value):
            if seen != ident:
                return
            answer['value'] = value
            done.set()

        self._waiting[ident] = action
        self.bridge.answered.connect(on_answer)
        try:
            self.bridge.asked.emit(ident, action, self.editable_for(action))
            while not done.wait(0.2):
                worker = self.worker
                if worker is not None and worker.isInterruptionRequested():
                    return False
            return answer.get('value', False)
        finally:
            self._waiting.pop(ident, None)
            try:
                self.bridge.answered.disconnect(on_answer)
            except (RuntimeError, TypeError):
                pass

    def editable_for(self, action) -> dict:
        """The arguments of the proposed call the owner may change."""
        raw = getattr(action, 'arguments', '')
        if not raw:
            return {}
        try:
            arguments = json.loads(raw)
        except ValueError:
            return {}
        if not isinstance(arguments, dict):
            return {}
        editable = {}
        for key, value in arguments.items():
            if isinstance(value, (str, int, float, bool)):
                editable[key] = value
        return editable

    def answer(self, ident: str, value) -> bool:
        """Deliver the owner's answer to the mission that is waiting."""
        if ident not in self._waiting:
            return False
        self.bridge.answered.emit(ident, value)
        return True

    # ------------------------------------------------------------------

    def on_engine_record(self, record):
        """Move the record of one step to the interface."""
        self.engine_used.emit(record)

    def on_event(self, event):
        """Move one step of the mission to the console."""
        self.panel.append_event(event)
        if event.step:
            self._step = event.step
            # The counter is the mission's step of its budget, and it is
            # the same number before and after the mission.
            self.panel.set_counter(event.step, self.max_steps)
            self.step_changed.emit(event.step, self.max_steps)
        if event.kind == 'tool':
            self._steps += 1
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


__all__ = ['ApprovalBridge', 'MissionController']
