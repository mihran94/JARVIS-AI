"""Run one coding task inside an isolated worktree and report a reviewable diff.

WHAT THIS IS
    The owner says "fix the login page validation in project-a". JARVIS opens
    the project, asks Codex to make that change, runs the project's own tests
    and shows the owner the diff. That is the whole point of the product: the
    next step after "open the app" is doing useful work INSIDE the project and
    proving it.

HOW THE WORK IS ISOLATED
    The change is made in a throwaway Git worktree created from the project's
    HEAD, never in the owner's working folder. So:

    * the owner's uncommitted work is untouched, and JARVIS says so;
    * the diff is a real Git diff against the project's own history, which is
      what the owner reviews;
    * the tests run against the changed code, in the same place the change
      was made.

    A folder that is not a Git repository cannot be isolated and cannot give a
    reviewable diff, so the task is refused with a clear reason instead of
    editing the owner's files in place.

WHAT NEEDS APPROVAL
    The owner approves the whole task once, in chat, before anything starts:
    the project, the change and the steps are all shown. Nothing is installed,
    nothing is pushed, nothing is merged, and no project data is sent to a
    provider that the owner has not already chosen.

WHAT THIS MODULE WILL NOT DO
    * It never edits the owner's working folder.
    * It never runs a shell. The configured test command is split into
      arguments and run directly.
    * It never continues after a cancellation. An emergency stop leaves the
      worktree on disk for the owner to look at, and the task stays cancelled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shlex
import subprocess
import time
import uuid

from core.protection import Protection
from developer_studio.codex_cli import codex_executable, run_codex


#: The steps a task goes through. The card shows them and marks them done.
TASK_STEPS = (
    'open_project',
    'isolate_worktree',
    'read_and_edit',
    'collect_diff',
    'run_tests',
    'report',
)

STEP_LABELS = {
    'open_project': 'Open the project in the chosen editor',
    'isolate_worktree': 'Create an isolated worktree so your files stay untouched',
    'read_and_edit': 'Ask Codex to read the project and make the change',
    'collect_diff': 'Collect the reviewable diff',
    'run_tests': 'Run the configured local tests',
    'report': 'Report the changed files, the diff and the test results',
}


@dataclass
class TaskOutcome:
    """Everything the chat needs to show about one finished task."""

    status: str = 'completed'
    steps: list[str] = field(default_factory=list)
    diff: str = ''
    changed_files: list[str] = field(default_factory=list)
    test_status: str = 'not run'
    test_output: str = ''
    message: str = ''
    worktree: str = ''
    protected: list[str] = field(default_factory=list)
    answer: str = ''
    #: The commit the task started from. Every change is reported against it.
    starting_commit: str = ''
    #: The protected files the task tried to change. They are put back.
    refused: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            'status': self.status,
            'steps': list(self.steps),
            'diff': self.diff,
            'changed_files': list(self.changed_files),
            'test_status': self.test_status,
            'test_output': self.test_output,
            'message': self.message,
            'worktree': self.worktree,
            'protected': list(self.protected),
            'starting_commit': self.starting_commit,
            'refused': list(self.refused),
        }


def split_test_command(command: str, *, windows=None) -> list[str]:
    """Parse an approved test command without a shell on either platform.

    Windows shlex preserves delimiting double quotes, which must be
    removed before passing an argv list to Popen. We preserve the internal
    backslashes of Windows executable paths and Python -c arguments.
    """
    if windows is None:
        windows = os.name == 'nt'
    arguments = shlex.split(command, posix=not windows)
    if windows:
        arguments = [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part
            for part in arguments
        ]
    return arguments


def run_local_tests(folder, command: str, timeout: int = 1800, cancel=None, observer=None):
    """Run a project's own configured tests in that folder.

    The command is split into arguments and run directly. There is no shell,
    so a configured test command cannot become another command.

    `cancel` is called while the tests run. If it raises — which is how
    Emergency Stop is signalled — the test process is TERMINATED, not left
    running in the background while the owner believes it stopped. The
    function then reports the run as cancelled.

    `observer` is called with the running process, so a caller can see that
    the process really went away.
    """
    command = (command or '').strip()
    if not command:
        return 'not configured', 'No test command is configured for this project.'
    try:
        arguments = split_test_command(command)
    except ValueError:
        arguments = command.split()
    if not arguments:
        return 'not configured', 'The configured test command was empty.'
    try:
        process = subprocess.Popen(
            arguments, cwd=str(folder), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError) as error:
        return 'could not run', str(error)
    if observer is not None:
        observer(process)
    try:
        while True:
            if cancel is not None:
                cancel()
            if process.poll() is not None:
                break
            time.sleep(0.1)
    except BaseException:
        _stop_process(process)
        raise
    output = process.stdout.read() if process.stdout else ''
    return ('passed' if process.returncode == 0 else 'failed'), (output or '')[-8000:]


def _stop_process(process):
    """Stop a running test process and wait for it to go away."""
    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass
    except (OSError, subprocess.SubprocessError):
        pass


def git_output(folder, *args):
    """Run a read-only Git command and return its output, or None."""
    try:
        result = subprocess.run(['git', '-C', str(folder), *args], capture_output=True,
                                text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    return result.stdout


def is_git_repo(folder: Path) -> bool:
    output = git_output(folder, 'rev-parse', '--is-inside-work-tree')
    return bool(output and output.strip() == 'true')


def uncommitted_files(folder: Path) -> list[str]:
    output = git_output(folder, 'status', '--porcelain')
    if not output:
        return []
    return [line for line in output.splitlines() if line.strip()]


def build_prompt(project, change: str, protection=None) -> str:
    """The instruction Codex receives.

    It says exactly what the owner asked for, and it says that the work must
    stay inside this folder and must not touch the network.

    When the project has files that hold secrets, or that its own
    `.gitignore` keeps out, they are named here. The model is told what is
    off limits instead of being trusted to guess.
    """
    notice = ''
    if protection is not None:
        notice = protection.notice()
    return (
        f"Work only inside this project folder. The owner asked for this change:\n\n"
        f"{change}\n\n"
        "Read the project first and understand how it is put together before you change "
        "anything. Make the smallest change that does what was asked, match the style and "
        "the structure that is already there, and do not add anything that was not asked "
        "for. Do not install packages, do not push, do not merge, and do not reach the "
        "network. If the request is ambiguous, make the most reasonable reading of it and "
        "say in your answer what you assumed."
        + (f"\n\n{notice}" if notice else "")
    )


class CodexTask:
    """One coding task, from the request to the reviewable diff."""

    def __init__(self, project, change: str, *, test_command: str = '',
                 worktree_root=None, progress=None, check_cancelled=None,
                 codex_path=None):
        self.project = project
        self.change = (change or '').strip()
        self.test_command = (test_command or '').strip()
        self.worktree_root = Path(worktree_root) if worktree_root else None
        self.progress = progress or (lambda step, text: None)
        self.check_cancelled = check_cancelled or (lambda: None)
        self.codex_path = codex_path
        self.outcome = TaskOutcome()

    # -- helpers ----------------------------------------------------------

    def _step(self, step, text):
        self.outcome.steps.append(step)
        self.progress(step, text)

    def _blocked(self, message):
        self.outcome.status = 'blocked'
        self.outcome.message = message
        return self.outcome

    # -- the run ----------------------------------------------------------

    def run(self) -> TaskOutcome:
        self.check_cancelled()
        folder = Path(self.project.path)
        if not folder.is_dir():
            return self._blocked(f'The project folder {folder} is not there any more.')

        self._step('open_project', f'Opening {self.project.name} in {self.project.editor}.')

        if not is_git_repo(folder):
            return self._blocked(
                f'{folder} is not a Git repository, so JARVIS cannot make a reviewable change '
                'without editing your files in place. Start a Git repository in the project, '
                'or choose a different project.')

        protected = uncommitted_files(folder)
        self.outcome.protected = protected

        worktree = self._make_worktree(folder)
        if worktree is None:
            return self._blocked(
                'JARVIS could not create an isolated worktree for this project, so nothing '
                'was changed. Check that Git can write to this repository.')
        self.outcome.worktree = str(worktree)
        self._step('isolate_worktree',
                   f'Isolated worktree ready at {worktree}. Your uncommitted work is untouched.')
        # The commit the task starts from. Every change is reported against
        # it, so a task that commits as well as edits still shows the whole
        # difference and not just the last edit.
        self.outcome.starting_commit = (git_output(worktree, 'rev-parse', 'HEAD') or '').strip()

        try:
            self.check_cancelled()
        except Exception:
            self.outcome.status = 'cancelled'
            self.outcome.message = 'Cancelled before Codex started. Your project is untouched.'
            return self.outcome

        try:
            executable = self.codex_path or codex_executable()
        except ValueError as error:
            return self._blocked(str(error) + ' The worktree was left at ' + str(worktree))

        self._step('read_and_edit', 'Asking Codex to read the project and make the change.')
        try:
            protection = Protection(worktree)
            answer = run_codex(executable, folder,
                                build_prompt(self.project, self.change, protection),
                                self.check_cancelled, sandbox='workspace-write',
                                cwd=str(worktree), timeout=600)
        except Exception as error:
            if self._cancelled(error):
                self.outcome.status = 'cancelled'
                self.outcome.message = ('Cancelled. The worktree was left at ' + str(worktree)
                                         + ' for you to look at. Your project is untouched.')
                return self.outcome
            self.outcome.status = 'failed'
            self.outcome.message = str(error)
            self.outcome.worktree = str(worktree)
            return self.outcome
        self.outcome.answer = answer

        self._step('collect_diff', 'Collecting the reviewable diff.')
        diff, changed, refused = self._collect_diff(worktree, self.outcome.starting_commit)
        self.outcome.refused = refused
        if refused:
            self._step('restore_protected',
                       'Put back the protected files the task tried to change: '
                       + ', '.join(refused))
        self.outcome.diff = diff
        self.outcome.changed_files = changed

        if not changed:
            self.outcome.status = 'failed'
            self.outcome.message = ('Codex finished but changed nothing. The diff below is '
                                    'empty, so there is nothing to review.')
            return self.outcome

        if self.test_command:
            self._step('run_tests', f'Running: {self.test_command}')
            status, output = self._run_tests(worktree)
            self.outcome.test_status = status
            self.outcome.test_output = output
        else:
            self.outcome.test_status = 'not configured'
            self.outcome.test_output = ('No test command is configured for this project, so no '
                                        'tests were run.')

        self._step('report', 'Reporting the changed files, the diff and the test results.')
        self.outcome.status = 'completed'
        against = self.outcome.starting_commit[:8] if self.outcome.starting_commit else 'HEAD'
        self.outcome.message = (
            f'{len(changed)} file(s) changed against {against}. The diff is below and the '
            f'worktree is at {worktree}. Nothing was pushed, merged or installed.')
        return self.outcome

    # -- internals --------------------------------------------------------

    def _cancelled(self, error):
        return 'cancel' in str(error).casefold() or 'stopped' in str(error).casefold()

    def _make_worktree(self, folder: Path):
        """Create an isolated worktree from the project's HEAD."""
        root = self.worktree_root
        if root is None:
            return None
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        target = root / f'{self.project.name}-{uuid.uuid4().hex[:12]}'
        result = subprocess.run(
            ['git', '-C', str(folder), 'worktree', 'add', '--detach', str(target), 'HEAD'],
            capture_output=True, text=True, timeout=120)
        if result.returncode:
            return None
        return target if target.is_dir() else None

    def _collect_diff(self, worktree: Path, starting_commit: str = ''):
        """The reviewable diff, including files the task created.

        The diff is taken against the commit the task STARTED from, not
        against the worktree's current HEAD. A task that commits its own
        work would otherwise hide those edits behind the new commit, and the
        owner would review a diff that was missing half of the change.

        Everything is staged first, so uncommitted edits and files the task
        created are in the diff too.

        A file that holds secrets, or that the project's `.gitignore` keeps
        out, is put back and left out of the diff. Otherwise the review
        screen would show the contents of a key, and the transcript would
        keep it.
        """
        subprocess.run(['git', '-C', str(worktree), 'add', '-A'], capture_output=True,
                       timeout=60)
        base = [starting_commit] if starting_commit else []
        names = git_output(worktree, 'diff', '--name-only', '--cached', *base) or ''
        changed = [line.strip() for line in names.splitlines() if line.strip()]
        refused = self._restore_protected(worktree, changed)
        diff = git_output(worktree, 'diff', '--cached', *base) or ''
        changed = [name for name in changed if name not in refused]
        return diff, changed, refused

    def _restore_protected(self, worktree: Path, changed) -> list[str]:
        """Put back every protected file the task changed.

        The owner's own folder is never touched — the change was made in the
        worktree — but the diff would carry the contents of a key into the
        chat, so the file goes back and the owner is told.
        """
        protection = Protection(worktree)
        refused = []
        for name in changed:
            if not protection.blocked(name):
                continue
            # HEAD, not the index: the file was already staged, and the
            # index holds the change that has to be undone.
            subprocess.run(['git', '-C', str(worktree), 'checkout', 'HEAD', '--', name],
                           capture_output=True, timeout=60)
            refused.append(name)
        if refused:
            subprocess.run(['git', '-C', str(worktree), 'add', '-A'], capture_output=True,
                           timeout=60)
        return refused

    def _run_tests(self, worktree: Path):
        """Run the project's configured local tests, without a shell."""
        return run_local_tests(worktree, self.test_command)
