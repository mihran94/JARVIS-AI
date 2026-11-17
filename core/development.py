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

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import subprocess
import uuid

from core.candidates import content_digest as snapshot_digest
from core.updates import (MAX_EXPANDED, backup_history, read_state, release_path, stage_snapshot,
                          validate_update_path)
from core.verification import TestRunError, run_tests
from security.policy import Stopped

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
    base: str = 'base'

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
            'tests': dict(self.tests), 'reason': self.reason, 'prepared_at': self.prepared_at, 'base': self.base,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Improvement':
        return cls(
            ident=str(data.get('ident', '')), goal=str(data.get('goal', '')),
            provider=str(data.get('provider', '')), state=str(data.get('state', 'preparing')),
            worktree=str(data.get('worktree', '')), revision=str(data.get('revision', '')),
            digest=str(data.get('digest', '')), diff=str(data.get('diff', '')),
            changed=tuple(data.get('changed', ())), tests=dict(data.get('tests', {})),
            reason=str(data.get('reason', '')), prepared_at=str(data.get('prepared_at', '')), base=str(data.get('base', 'base')),
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
    _git(folder, 'add', '-A')
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


def snapshot_files(folder):
    """Read only files selected by Git, with the same path rules as updates."""
    folder = Path(folder).resolve()
    files = {}
    size = 0
    for record in _git(folder, 'ls-files', '--stage', '-z').split('\0'):
        if not record:
            continue
        metadata, name = record.split('\t', 1)
        mode, _, stage = metadata.split()
        validate_update_path(name)
        if (mode not in {'100644', '100755'} or stage != '0'
                or set(Path(name).parts) & {'.git', '.venv', '.updates', 'development'}):
            raise DevelopmentError('The improvement includes an unsupported source file.')
        path = folder / name
        if not path.is_file() or path.resolve() != path or path.is_symlink():
            raise DevelopmentError('A prepared source file moved or contains a link.')
        size += path.stat().st_size
        if size > MAX_EXPANDED:
            raise DevelopmentError('The prepared source exceeds the update size limit.')
        files[name] = path.read_bytes()
    return files


def manifest_paths(source):
    manifest = source / 'docs' / 'SOURCE_INTEGRITY.sha256'
    if not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size > 500_000:
        raise DevelopmentError('Use a JARVIS Git checkout or a source installation with its integrity manifest.')
    names = ['docs/SOURCE_INTEGRITY.sha256']
    for line in manifest.read_text('utf-8').splitlines():
        if line and not line.startswith('#'):
            digest, separator, name = line.partition('  ')
            if not separator or not re.fullmatch('[a-f0-9]{64}', digest):
                raise DevelopmentError('Invalid source manifest.')
            validate_update_path(name)
            names.append(name)
    return [source / name for name in names]


def seed_baseline(root, base, worktree):
    source = release_path(root, base)
    if not source.is_dir():
        raise DevelopmentError('The selected release is missing.')
    paths = manifest_paths(source) if base == 'base' else source.rglob('*')
    files = {}
    size = 0
    for path in paths:
        relative = path.relative_to(source)
        if set(relative.parts) & {'.pytest_cache', '__pycache__'}:
            continue
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise DevelopmentError('The selected release contains a link.')
        if path.is_file():
            name = relative.as_posix()
            validate_update_path(name)
            if (path.resolve() != path or set(relative.parts) & {'.git', '.venv', '.updates', 'development'}
                    or relative.parts[0].lower().startswith('.env')):
                raise DevelopmentError('The selected release contains an unsafe source file.')
            size += path.stat().st_size
            if size > MAX_EXPANDED:
                raise DevelopmentError('The selected release exceeds the source size limit.')
            files[name] = path.read_bytes()
    for name in snapshot_files(worktree):
        if name not in files:
            (worktree / name).unlink()
    for name, content in files.items():
        path = worktree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    _git(worktree, 'add', '-f', '--all')
    _git(worktree, '-c', 'user.name=JARVIS', '-c', 'user.email=jarvis@localhost',
         '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
         'commit', '--allow-empty', '-m', 'Baseline from the selected JARVIS release')


def content_digest(folder) -> str:
    return snapshot_digest(snapshot_files(folder))


def prepare_improvement(root, repo, goal: str, provider: str, ident: str = '', *,
                        change=None, test_command: str = '', timeout: int = 1800,
                        check=lambda: None, resume=False) -> Improvement:
    """Prepare one improvement in an isolated worktree.

    `change` is called with the worktree and makes the edit; it is the
    coding provider doing the work. `test_command` is run in the worktree
    afterwards. Both are passed in so the caller controls which provider is
    used and so this module never talks to a provider itself.
    """
    ident = ident or uuid.uuid4().hex
    target = worktree_for(root, ident)
    base = read_state(root)['active']
    if resume and target.is_dir():
        expected_repo = repo if is_repository(repo) else target
        if (target.is_symlink() or not is_repository(target)
                or _git(target, 'rev-parse', '--path-format=absolute', '--git-common-dir')
                != _git(expected_repo, 'rev-parse', '--path-format=absolute', '--git-common-dir')):
            raise DevelopmentError('The saved folder is not a worktree of this installation.')
        revision = current_revision(target)
    elif is_repository(repo):
        revision = create_worktree(repo, target)
        if base != 'base':
            seed_baseline(root, base, target)
            revision = current_revision(target)
    else:
        if base == 'base':
            manifest_paths(Path(root).resolve())
        target.mkdir(parents=True)
        _git(target, 'init')
        seed_baseline(root, base, target)
        revision = current_revision(target)
    check()
    tests: dict = {}
    reason = ''
    if change is not None:
        try:
            change(target, provider, goal)
        except Stopped:
            raise
        except Exception as error:  # the provider failed; the worktree stays
            # A classified provider failure travels on as it is, so the caller
            # can tell a rate limit from a wrong request.
            if getattr(error, 'diagnosis', None) is not None:
                raise
            raise DevelopmentError(str(error)) from error
    check()
    diff = worktree_diff(target)
    digest = content_digest(target)
    if test_command:
        try:
            tests = run_tests(target, test_command, timeout=timeout, cancel=check)
        except TestRunError as error:
            tests = {'status': 'error', 'summary': str(error), 'output': ''}
    if content_digest(target) != digest:
        tests = {'status': 'failed', 'summary': 'The tests changed the prepared source.'}
    return Improvement(
        ident=ident, goal=goal, provider=provider,
        state='ready',
        worktree=str(target), revision=revision, digest=digest, base=base,
        diff=diff, changed=worktree_changed(target), tests=tests,
        reason=reason,
        prepared_at=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
    )


def test_improvement(improvement, command, *, check):
    check()
    if content_digest(improvement.worktree) != improvement.digest:
        raise DevelopmentError('The code changed after the review. Prepare it again.')
    try:
        tests = run_tests(improvement.worktree, command, cancel=check)
    except TestRunError as error:
        tests = {'status': 'error', 'summary': str(error), 'output': ''}
    check()
    if content_digest(improvement.worktree) != improvement.digest:
        raise DevelopmentError('The tests changed the prepared source. Prepare it again.')
    return replace(improvement, tests=tests)


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


def apply_improvement(improvement: Improvement, *, root=None, history=None,
                      check=lambda: None, publish=lambda operation: operation()) -> str:
    """Stage the exact tested snapshot and keep the current version for rollback."""
    approve_improvement(improvement)
    if root is None or history is None:
        raise DevelopmentError('An installation and history database are required.')
    expected_worktree = worktree_for(root, improvement.ident).resolve()
    if Path(improvement.worktree).resolve() != expected_worktree:
        raise DevelopmentError('The prepared worktree does not belong to this installation.')
    files = snapshot_files(expected_worktree)
    if snapshot_digest(files) != improvement.digest:
        raise DevelopmentError('The code changed after the review. Review it again.')
    state = read_state(root)
    if state['active'] != improvement.base:
        raise DevelopmentError('The selected version changed. Prepare this improvement again.')
    if state['active'] == improvement.digest:
        return 'This improvement is already selected.'
    backup_history(history)
    return stage_snapshot(root, improvement.digest, files, expected_state=state,
                          check=check, publish=publish)


def reject_improvement(improvement: Improvement) -> str:
    """Throw the prepared change away. The running code is untouched."""
    return f'Change {improvement.short} was rejected. The running version is unchanged.'


def maintenance_goal(folder):
    root = Path(folder)
    guide = root / 'docs' / 'UPDATES.md'
    if guide.is_symlink() or not guide.is_file() or guide.stat().st_size > 100_000:
        return ''
    text = guide.read_text(encoding='utf-8')
    missing = [name for name in ('START_JARVIS.cmd', 'ROLLBACK_JARVIS.cmd')
               if (root / name).is_file() and name not in text]
    if missing:
        return ('Update only docs/UPDATES.md to document the existing Windows script(s): '
                + ', '.join(missing) + '. Keep the existing instructions.')
    return ''
