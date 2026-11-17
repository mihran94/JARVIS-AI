"""JARVIS preparing an improvement to its own source, in an isolated worktree.

THE WORKFLOW
    1. The owner asks for a scoped improvement to JARVIS itself.
    2. JARVIS makes a Git worktree for it under the local `development/`
       folder, from the current commit. The running installation is never
       the place where the change is made.
    3. The coding provider — MiniMax or Codex, never anything else — makes
       the change inside that worktree.
    4. The relevant tests run in the worktree.
    5. The diff, the test results and the exact revision are saved, so the
       owner can read what happened and decide.
    6. The owner approves that exact revision. If the worktree changes after
       the approval, the approval is refused and the change is reviewed
       again.

INTERRUPTED WORK
    Every step is written down before it happens, so a task that stops — a
    rate limit, a closed window, a stopped run — can be picked up again
    from the worktree that is already there.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import uuid

from core.verification import TestRunError, run_tests

DEVELOPMENT_FOLDER = 'development'


class DevelopmentError(RuntimeError):
    """The improvement could not be prepared."""


@dataclass(frozen=True)
class Improvement:
    """One prepared improvement, waiting for the owner's decision."""

    ident: str
    goal: str
    provider: str
    state: str = 'preparing'
    worktree: str = ''
    revision: str = ''
    digest: str = ''
    diff: str = ''
    changed: tuple[str, ...] = ()
    tests: dict = field(default_factory=dict)
    reason: str = ''
    prepared_at: str = ''

    @property
    def short(self) -> str:
        return self.revision[:12] if self.revision else self.ident[:12]

    @property
    def tests_passed(self) -> bool:
        return str(self.tests.get('status', '')).lower() == 'passed'

    @property
    def resumable(self) -> bool:
        """True when this task can be picked up again."""
        return self.state in ('pending', 'waiting', 'failed')

    @property
    def waiting(self) -> bool:
        """True when the task stopped for a reason that may pass."""
        return self.state == 'waiting'

    @property
    def appliable(self) -> bool:
        """True when the owner may apply this improvement.

        A change whose tests failed is never appliable.
        """
        return bool(self.tests) and self.tests_passed

    def as_dict(self) -> dict:
        return {
            'ident': self.ident, 'goal': self.goal, 'provider': self.provider,
            'state': self.state, 'worktree': self.worktree, 'revision': self.revision,
            'digest': self.digest, 'diff': self.diff, 'changed': list(self.changed),
            'tests': dict(self.tests), 'reason': self.reason, 'prepared_at': self.prepared_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Improvement':
        return cls(
            ident=str(data.get('ident', '')), goal=str(data.get('goal', '')),
            provider=str(data.get('provider', '')), state=str(data.get('state', 'preparing')),
            worktree=str(data.get('worktree', '')), revision=str(data.get('revision', '')),
            digest=str(data.get('digest', '')), diff=str(data.get('diff', '')),
            changed=tuple(data.get('changed', ())), tests=dict(data.get('tests', {})),
            reason=str(data.get('reason', '')), prepared_at=str(data.get('prepared_at', '')),
        )


def development_root(root) -> Path:
    """The local folder the prepared improvements live in."""
    return Path(root) / DEVELOPMENT_FOLDER


def worktree_for(root, ident: str) -> Path:
    """Where the worktree of one improvement lives."""
    return development_root(root) / ident


def slug(text: str, ident: str) -> str:
    """A short, safe folder name for a goal."""
    words = re.findall(r'[a-zA-Z0-9]+', (text or '').lower())[:4]
    name = '-'.join(words) or 'improvement'
    return f'{name[:40]}-{ident[:8]}'


def _git(folder, *args, timeout: int = 120) -> str:
    result = subprocess.run(
        ['git', '-C', str(folder), *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise DevelopmentError(result.stderr.strip() or 'Git could not complete the request.')
    return result.stdout.strip()


def is_repository(folder) -> bool:
    """True when the folder is a Git checkout JARVIS may work in."""
    path = Path(folder)
    return (path / '.git').exists() or (path / '.git').is_file()


def current_revision(folder) -> str:
    """The commit the improvement is made against."""
    return _git(folder, 'rev-parse', 'HEAD')


def create_worktree(repo, target: Path) -> str:
    """Create the isolated worktree and return the revision it was made from.

    The worktree is detached, so the branch that is checked out in the
    repository is never moved by the work that happens inside it.
    """
    repo = Path(repo)
    if not is_repository(repo):
        raise DevelopmentError(
            'This installation is not a Git checkout, so JARVIS cannot prepare an improvement here.')
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    revision = current_revision(repo)
    result = subprocess.run(
        ['git', '-C', str(repo), 'worktree', 'add', '--detach', str(target), revision],
        capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise DevelopmentError(result.stderr.strip() or 'The worktree could not be created.')
    return revision


def remove_worktree(repo, target: Path) -> None:
    """Remove a worktree that is no longer needed."""
    target = Path(target)
    if not target.exists():
        return
    repo = Path(repo)
    if is_repository(repo):
        subprocess.run(['git', '-C', str(repo), 'worktree', 'remove', '--force', str(target)],
                       capture_output=True, text=True, timeout=120)
    shutil.rmtree(target, ignore_errors=True)


def worktree_diff(folder) -> str:
    """The diff of the worktree against the commit it was made from."""
    folder = Path(folder)
    if not folder.is_dir():
        return ''
    subprocess.run(['git', '-C', str(folder), 'add', '-A'], capture_output=True, timeout=120)
    return _git(folder, 'diff', '--cached') + ''


def discard_empty_worktree(repo, target: Path) -> bool:
    """Remove a worktree that holds no change.

    A provider that stopped before it changed anything leaves a worktree that
    is the same as the checkout. It is removed, so the installation does not
    collect empty worktrees. A worktree that holds a change is kept, because
    that is where the work is.
    """
    target = Path(target)
    if not target.is_dir():
        return False
    if worktree_changed(target):
        return False
    remove_worktree(repo, target)
    return True


def worktree_changed(folder) -> tuple[str, ...]:
    """The files the change touched."""
    folder = Path(folder)
    if not folder.is_dir():
        return ()
    names = _git(folder, 'diff', '--cached', '--name-only')
    return tuple(name for name in names.splitlines() if name.strip())


def content_digest(folder) -> str:
    """One digest for everything in the worktree, so any change is visible."""
    digest = hashlib.sha256()
    for path in sorted(Path(folder).rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or '.git' in path.parts:
            continue
        digest.update(str(path.relative_to(folder)).encode('utf-8'))
        digest.update(b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def prepare_improvement(root, repo, goal: str, provider: str, ident: str = '', *,
                        change=None, test_command: str = '', timeout: int = 1800,
                        check=lambda: None) -> Improvement:
    """Prepare one improvement in an isolated worktree.

    `change` is called with the worktree and makes the edit; it is the
    coding provider doing the work. `test_command` is run in the worktree
    afterwards. Both are passed in so the caller controls which provider is
    used and so this module never talks to a provider itself.
    """
    ident = ident or uuid.uuid4().hex
    target = worktree_for(root, ident)
    revision = create_worktree(repo, target)
    check()
    tests: dict = {}
    reason = ''
    if change is not None:
        try:
            change(target, provider, goal)
        except Exception as error:  # the provider failed; the worktree stays
            # A classified provider failure travels on as it is, so the caller
            # can tell a rate limit from a wrong request.
            if getattr(error, 'diagnosis', None) is not None:
                raise
            raise DevelopmentError(str(error)) from error
    check()
    if test_command:
        try:
            tests = run_tests(target, test_command, timeout=timeout, cancel=check)
        except TestRunError as error:
            tests = {'status': 'error', 'summary': str(error), 'output': ''}
    return Improvement(
        ident=ident, goal=goal, provider=provider,
        state='ready' if tests.get('status') == 'passed' else 'failed',
        worktree=str(target), revision=revision, digest=content_digest(target),
        diff=worktree_diff(target), changed=worktree_changed(target), tests=tests,
        reason=reason,
        prepared_at=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
    )


def approve_improvement(improvement: Improvement) -> None:
    """Check that the worktree is still exactly what the owner reviewed."""
    if not improvement.worktree:
        raise DevelopmentError('There is no prepared change to approve.')
    if not Path(improvement.worktree).is_dir():
        raise DevelopmentError('The worktree for this change is gone. Prepare it again.')
    if content_digest(Path(improvement.worktree)) != improvement.digest:
        raise DevelopmentError('The code changed after the review. Review it again.')
    if not improvement.appliable:
        raise DevelopmentError('The tests for this change failed, so it cannot be applied.')


def apply_improvement(improvement: Improvement) -> str:
    """Accept the reviewed change. The worktree is kept for the owner."""
    approve_improvement(improvement)
    return (f'Change {improvement.short} is ready to apply. '
            'The worktree with the change is kept for you to look at.')


def reject_improvement(improvement: Improvement) -> str:
    """Throw the prepared change away. The running code is untouched."""
    return f'Change {improvement.short} was rejected. The running version is unchanged.'
