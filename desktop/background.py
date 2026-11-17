"""Background work: preparing an improvement, and checking for a source update.

The work runs off the interface thread, so the window stays usable while a
provider is thinking or a test suite is running. Every step is saved as it
happens, so an interrupted run can be picked up again from the worktree that
is already there.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.candidates import prepare_candidate, test_candidate
from core.coding_agent import CodingAgentError, apply_files, ask
from core.coding_tasks import create as create_task, set_state, save as save_task, load as load_task
from core.development import DevelopmentError, Improvement, prepare_improvement, test_improvement, worktree_for
from core.updates import UpdateError, read_state
from providers.errors import FailureKind
from providers.routing import other_coding_provider, require_coding_provider
from security.policy import Stopped


class ImprovementWorker(QThread):
    """Prepares one improvement to JARVIS in an isolated worktree."""

    prepared = Signal(object)
    message = Signal(str)
    stopped = Signal(str)

    def __init__(self, window, goal: str, provider: str, parent=None, *, automatic=False, task=None):
        super().__init__(parent)
        self.window = window
        self.goal = goal
        self.provider = provider
        self.automatic = automatic
        self.task = task
        self.ticket = window.policy.ticket()

    def check(self):
        if self.isInterruptionRequested():
            raise Stopped()
        self.window.policy.check(self.ticket)

    def run(self):
        store = self.window.store
        try:
            require_coding_provider(self.provider)
        except ValueError as error:
            self.message.emit(str(error))
            return
        try:
            root = self.window.installation_root()
            repo = Path(root)
            base = read_state(root)['active']
            resumed = self.task is not None
            if resumed and self.task.base != base:
                raise DevelopmentError('The active version changed. Prepare a new improvement for it.')
            self.task = self.task or create_task(store, self.goal, self.provider)
            self.task = save_task(store, replace(self.task, provider=self.provider, state='running',
                                                 worktree=str(worktree_for(root, self.task.ident)),
                                                 reason='', base=base))

            def make_change(worktree, provider, goal):
                files = ask(provider, goal, worktree, check=self.check,
                            model=self.window.coding_model(provider),
                            key=self.window.coding_key(provider))
                if self.automatic and set(files) != {'docs/UPDATES.md'}:
                    raise DevelopmentError('Automatic maintenance can only edit docs/UPDATES.md.')
                self.check()
                apply_files(worktree, files)

            improvement = prepare_improvement(
                root, repo, self.goal, self.provider, ident=self.task.ident,
                change=make_change, check=self.check, resume=resumed)
            saved = save_task(store, improvement)
            self.prepared.emit(saved)
            self.message.emit(self._summary(saved))
        except Stopped:
            if self.task is not None:
                set_state(store, self.task, 'waiting', 'The task was paused and can be retried.')
            self.message.emit('Preparation paused.')
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
                 parent=None, *, candidate=None):
        super().__init__(parent)
        self.candidate = candidate
        self.root = root
        self.running_root = running_root
        self.history = history
        self.policy = policy
        self.ticket = ticket
        self.test_command = test_command

    def check(self):
        if self.isInterruptionRequested():
            raise Stopped()
        self.policy.check(self.ticket)

    def run(self):
        try:
            publish = lambda operation: self.policy.run_if_current(self.ticket, operation)
            if self.candidate is None:
                candidate = prepare_candidate(self.root, self.running_root, self.history,
                                              check=self.check, publish=publish)
            elif isinstance(self.candidate, Improvement):
                from core.store import Store
                store = Store(self.history)
                if load_task(store, self.candidate.ident) != self.candidate:
                    raise DevelopmentError('The prepared improvement changed. Review it again.')
                candidate = test_improvement(self.candidate, self.test_command, check=self.check)
                publish(lambda: save_task(store, candidate))
            else:
                candidate = test_candidate(self.root, self.candidate, self.test_command,
                                           check=self.check, publish=publish)
            self.prepared.emit(candidate)
            status = candidate.tests.get('status', 'not run')
            self.message.emit(f'Revision {candidate.short}: tests {status}.')
        except UpdateError as error:
            self.message.emit(str(error))
        except Exception as error:
            self.message.emit(f'The source check failed: {error}')
