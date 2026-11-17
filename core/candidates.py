"""A source update that is prepared, reviewed, and only then staged.

WHY THIS EXISTS
    PR #30 downloaded the latest commit on `main` and selected it for the
    next start. The owner requirement for that draft says the opposite:

        "Automatic download and test preparation must leave the active version
         pointer alone." and "Bind one-time approval to the exact verified
         revision. Changes after approval require a fresh review."

    So the automatic check no longer selects anything. It downloads the
    commit, verifies it against the GitHub tree, runs the tests in the
    prepared folder and writes down what it found. The version that runs
    only changes when the owner approves that exact revision.

THE RULES THIS MODULE KEEPS
    * Preparing never changes the version that runs.
    * An approval is bound to one revision and one content digest. If the
      prepared files change after the approval, the approval is refused and
      the change has to be reviewed again.
    * Only the approved revision is staged, and the version it replaces is
      kept so it can be rolled back.
    * A candidate whose tests failed can be reviewed, but it cannot be
      applied. The caller sees `appliable` and the interface disables Apply.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from core.updates import (UpdateError, backup_history, read_state, release_path, stage_snapshot)
from core.verification import TestRunError, run_tests

CANDIDATE_FILE = 'candidate.json'
CANDIDATE_FOLDER = 'candidates'


@dataclass(frozen=True)
class Candidate:
    """One prepared source revision, waiting for the owner's decision."""

    revision: str
    digest: str
    base: str
    changed: tuple[str, ...] = ()
    tests: dict = field(default_factory=dict)
    prepared_at: str = ''
    summary: str = ''

    @property
    def short(self) -> str:
        """The revision, shortened for a line of text."""
        return self.revision[:12]

    @property
    def tests_passed(self) -> bool:
        """True when the tests in the prepared folder passed."""
        return str(self.tests.get('status', '')).lower() == 'passed'

    @property
    def appliable(self) -> bool:
        """True when this candidate may be selected for the next start.

        A candidate whose tests failed is never appliable: the owner sees the
        failure and the Apply button stays disabled.
        """
        return bool(self.tests) and self.tests_passed

    def as_dict(self) -> dict:
        return {
            'revision': self.revision, 'digest': self.digest, 'base': self.base,
            'changed': list(self.changed), 'tests': dict(self.tests),
            'prepared_at': self.prepared_at, 'summary': self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Candidate':
        return cls(
            revision=str(data.get('revision', '')),
            digest=str(data.get('digest', '')),
            base=str(data.get('base', '')),
            changed=tuple(data.get('changed', ())),
            tests=dict(data.get('tests', {})),
            prepared_at=str(data.get('prepared_at', '')),
            summary=str(data.get('summary', '')),
        )


def candidate_folder(root) -> Path:
    """Where the prepared files of the pending candidate live."""
    return Path(root) / '.updates' / CANDIDATE_FOLDER


def candidate_file(root) -> Path:
    """Where the record of the pending candidate lives."""
    return Path(root) / '.updates' / CANDIDATE_FILE


def read_candidate(root) -> Candidate | None:
    """The candidate waiting for a decision, or None."""
    path = candidate_file(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text('utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get('revision'):
        return None
    return Candidate.from_dict(data)


def write_candidate(root, candidate: Candidate) -> None:
    """Record the pending candidate."""
    folder = Path(root) / '.updates'
    folder.mkdir(exist_ok=True)
    path = candidate_file(root)
    fd, tmp = tempfile.mkstemp(prefix='candidate-', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(candidate.as_dict(), out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def clear_candidate(root) -> None:
    """Forget the pending candidate and its prepared files."""
    path = candidate_file(root)
    if path.is_file():
        path.unlink()
    folder = candidate_folder(root)
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)


def prepared_path(root, revision: str) -> Path:
    """Where the files of one revision are kept."""
    return candidate_folder(root) / revision


def store_prepared(root, revision: str, files: dict) -> Path:
    """Write the prepared files so they can be reviewed and staged later."""
    target = prepared_path(root, revision)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for name, content in files.items():
        out = target / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(content)
    return target


def prepared_files(root, revision: str) -> dict:
    """Read the prepared files back."""
    target = prepared_path(root, revision)
    if not target.is_dir():
        raise UpdateError('The prepared source is no longer there. Check again.')
    files = {}
    for path in sorted(target.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            files[str(path.relative_to(target)).replace(os.sep, '/')] = path.read_bytes()
    return files


def content_digest(files: dict) -> str:
    """One digest for a set of files, so a change of any byte is visible."""
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode('utf-8'))
        digest.update(b'\0')
        digest.update(hashlib.sha256(files[name]).digest())
    return digest.hexdigest()


def prepare_candidate(root, running_root, history, *, check, publish, transport=None,
                       test_command: str = '', test_timeout: int = 1800) -> Candidate:
    """Download, verify and test a revision, and record it for review.

    The version that runs is not touched. The caller approves the candidate
    afterwards, and only then does the active pointer move.
    """
    from core.source_updates import fetch_latest_source

    state = read_state(root)
    if release_path(root, state['active']) != Path(running_root).resolve():
        raise UpdateError('A version is already selected. Restart from START_JARVIS.cmd to use it.')
    revision, _archive_digest, files = fetch_latest_source(root, check=check, transport=transport)
    check()
    # The candidate is identified by its content, so an approval is bound to
    # the bytes that were reviewed.
    digest = content_digest(files)
    if revision == state.get('last_source_revision') and read_candidate(root) is None:
        return Candidate(revision=revision, digest=digest, base=state['active'],
                         summary='This revision is the one that is already running.')
    from core.updates import changed_files
    current = release_path(root, state['active'])
    changed = tuple(changed_files(current, files))
    store_prepared(root, revision, files)
    tests = {}
    if test_command:
        tests = _test_prepared(root, revision, test_command, test_timeout, check)
    candidate = Candidate(
        revision=revision, digest=digest, base=state['active'], changed=changed,
        tests=tests,
        prepared_at=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        summary=describe(candidate_tests=tests, changed=changed),
    )
    check()

    def record():
        write_candidate(root, candidate)

    # The record is written through the same gate as every other change, so
    # an emergency stop cannot leave a half-prepared candidate behind.
    publish(record)
    return candidate


def _test_prepared(root, revision: str, command: str, timeout: int, check) -> dict:
    """Run the tests in the prepared folder and keep the outcome."""
    folder = prepared_path(root, revision)
    try:
        result = run_tests(folder, command, timeout=timeout, cancel=check)
    except TestRunError as error:
        return {'status': 'error', 'summary': str(error), 'output': ''}
    return result


def describe(*, candidate_tests: dict, changed) -> str:
    """One line for the status bar."""
    count = len(changed)
    files = 'file' if count == 1 else 'files'
    status = str(candidate_tests.get('status', 'not run'))
    return f'{count} {files} changed · tests {status}'


def approve_candidate(root, candidate: Candidate) -> None:
    """Check that the candidate is still exactly what was reviewed.

    The owner approves a revision, not a moment. If the prepared files
    changed after the review, the approval is refused and the revision has
    to be reviewed again.
    """
    if not candidate.revision:
        raise UpdateError('There is no prepared revision to approve.')
    files = prepared_files(root, candidate.revision)
    if content_digest(files) != candidate.digest:
        raise UpdateError('The prepared source changed after the review. Review it again.')
    if not candidate.appliable:
        raise UpdateError('The tests for this revision failed, so it cannot be applied.')


def stage_candidate(root, history, candidate: Candidate, *, check=lambda: None,
                    publish=lambda operation: operation()) -> str:
    """Select the approved revision for the next start.

    The previous version is kept, so it can be rolled back, and the owner's
    history is backed up before the code changes.
    """
    approve_candidate(root, candidate)
    files = prepared_files(root, candidate.revision)
    state = read_state(root)
    if state['active'] == candidate.digest:
        return 'This revision is already selected for the next start.'
    backup_history(history)
    message = stage_snapshot(root, candidate.digest, files, revision=candidate.revision,
                             expected_state=state, check=check, publish=publish)
    clear_candidate(root)
    return message


def reject_candidate(root, candidate: Candidate) -> str:
    """Throw the prepared revision away. The running version is untouched."""
    clear_candidate(root)
    return f'Revision {candidate.short} was rejected. The running version is unchanged.'
