"""Background work: preparing an improvement, and checking for a source update.

The work runs off the interface thread, so the window stays usable while a
provider is thinking or a test suite is running. Every step is saved as it
happens, so an interrupted run can be picked up again from the worktree that
is already there.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.candidates import prepare_candidate
from core.coding_agent import CodingAgentError, apply_files, ask, project_context
from core.coding_tasks import create as create_task, set_state, save as save_task
from core.development import DevelopmentError, prepare_improvement
from core.updates import UpdateError
from providers.errors import FailureKind
from providers.routing import other_coding_provider, require_coding_provider


class ImprovementWorker(QThread):
    """Prepares one improvement to JARVIS in an isolated worktree."""

    prepared = Signal(object)
    message = Signal(str)
    stopped = Signal(str)

    def __init__(self, window, goal: str, provider: str, parent=None):
        super().__init__(parent)
        self.window = window
        self.goal = goal
        self.provider = provider
        self.task = None

    def check(self):
        if self.isInterruptionRequested():
            from security.policy import Stopped
            raise Stopped()
        self.window.policy.check(self.window.policy.ticket())

    def run(self):
        store = self.window.store
        try:
            require_coding_provider(self.provider)
        except ValueError as error:
            self.message.emit(str(error))
            return
        self.task = create_task(store, self.goal, self.provider)
        set_state(store, self.task, 'running')
        try:
            root = self.window.installation_root()
            repo = Path(root)
            command = self.window.store.get('development_test_command') or 'python -m pytest -q'

            def make_change(worktree, provider, goal):
                files = ask(provider, goal, worktree, check=self.check,
                            model=self.window.coding_model(provider),
                            key=self.window.coding_key(provider))
                apply_files(worktree, files)

            improvement = prepare_improvement(
                root, repo, self.goal, self.provider, ident=self.task.ident,
                change=make_change, test_command=command, check=self.check)
            saved = save_task(store, improvement)
            self.prepared.emit(saved)
            self.message.emit(self._summary(saved))
        except CodingAgentError as error:
            self._failed(str(error))
        except DevelopmentError as error:
            self._failed(str(error))
        except Exception as error:
            from providers.chat import ProviderFailure
            diagnosis = getattr(error, 'diagnosis', None)
            if isinstance(error, ProviderFailure) and diagnosis is not None:
                self._provider_failure(diagnosis)
            else:
                self._failed(str(error))

    #: The failures that can pass, so the task is saved for another attempt.
    RESUMABLE_KINDS = (FailureKind.RATE_LIMIT, FailureKind.QUOTA, FailureKind.NETWORK,
                       FailureKind.TIMEOUT, FailureKind.TRANSIENT)

    def _provider_failure(self, diagnosis) -> None:
        """Save the task and say what the owner can do about it.

        A provider that is rate limited, out of quota or not reachable leaves
        the task in the state `waiting`, so it can be resumed. The other
        coding provider is offered, and using it needs the owner's approval.
        """
        store = self.window.store
        other = other_coding_provider(self.provider)
        if diagnosis.kind in self.RESUMABLE_KINDS:
            if self.task is not None:
                set_state(store, self.task, 'waiting', diagnosis.message)
            self._clean_empty_worktree()
            self.message.emit(
                f'{diagnosis.message} The task was saved and can be resumed. '
                f'Using {other} instead needs your approval.')
            return
        self._failed(f'{diagnosis.message} The task was saved and can be resumed.')

    def _failed(self, reason: str) -> None:
        store = self.window.store
        if self.task is not None:
            set_state(store, self.task, 'failed', reason)
        self.message.emit(reason)

    def _clean_empty_worktree(self) -> None:
        """Remove a worktree that holds no change, so none is left behind."""
        if self.task is None or not self.task.worktree:
            return
        from core.development import discard_empty_worktree
        try:
            discard_empty_worktree(Path(self.window.installation_root()), self.task.worktree)
        except Exception:
            pass

    def _summary(self, improvement) -> str:
        status = str(improvement.tests.get('status', 'not run'))
        return (f'Prepared {improvement.short} with {improvement.provider}. '
                f'Tests {status}. Review it before it is used.')


class SourceCheckWorker(QThread):
    """Downloads a source revision, verifies it and prepares it for review."""

    prepared = Signal(object)
    message = Signal(str)

    def __init__(self, root, running_root, history, policy, ticket, test_command='',
                 parent=None):
        super().__init__(parent)
        self.root = root
        self.running_root = running_root
        self.history = history
        self.policy = policy
        self.ticket = ticket
        self.test_command = test_command

    def check(self):
        if self.isInterruptionRequested():
            from security.policy import Stopped
            raise Stopped()
        self.policy.check(self.ticket)

    def run(self):
        try:
            candidate = prepare_candidate(
                self.root, self.running_root, self.history, check=self.check,
                publish=lambda operation: self.policy.run_if_current(self.ticket, operation),
                test_command=self.test_command)
            self.prepared.emit(candidate)
            self.message.emit(
                f'Revision {candidate.short} is prepared for review. '
                'The running version is unchanged until you approve it.')
        except UpdateError as error:
            self.message.emit(str(error))
        except Exception as error:
            self.message.emit(f'The source check failed: {error}')
