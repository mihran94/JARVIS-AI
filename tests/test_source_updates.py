"""Preparing a source revision for review, and approving that exact revision.

WHAT IS COVERED
    * Preparing a revision never changes the version that runs.
    * The prepared revision is verified against the GitHub tree before it is
      offered.
    * The tests run in the prepared folder, and their result is kept.
    * Approving selects that exact revision, and the version it replaces is
      kept so it can be rolled back.
    * A revision whose tests failed cannot be applied.
    * A prepared revision that changed after the review cannot be applied
      either: the approval has to be given again.
"""
import hashlib
from io import BytesIO
import json
import sqlite3
import zipfile

import httpx
import pytest

from core.candidates import (Candidate, approve_candidate, content_digest, prepare_candidate,
                             read_candidate, reject_candidate, stage_candidate, write_candidate)
from core.source_updates import API, ARCHIVES
from core.updates import UpdateError, read_state, release_path, rollback
from security.policy import Policy, Stopped

REVISION = 'a' * 40
TREE = 'b' * 40
FILES = {'requirements.txt': b'pinned==1\n', 'main.py': b'new code',
         'core/store.py': b'stable database', 'desktop/app.py': b'new UI',
         'START_JARVIS.cmd': b'@echo off\nexit /b 0\n'}


@pytest.fixture
def installation(tmp_path):
    root = tmp_path / 'install'
    for name, content in FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if name != 'main.py' else b'original code')
    history = tmp_path / 'history.sqlite3'
    with sqlite3.connect(history) as db:
        db.execute('CREATE TABLE history (message TEXT)')
        db.execute('INSERT INTO history VALUES (?)', ('retained',))
    return root, history


def fake_github(requests, *, files=FILES, archive_files=None, truncated=False):
    contents = BytesIO()
    with zipfile.ZipFile(contents, 'w') as archive:
        for name, data in (files if archive_files is None else archive_files).items():
            archive.writestr('JARVIS-AI-' + REVISION + '/' + name, data)
    tree = []
    for name, data in files.items():
        blob = hashlib.sha1(f'blob {len(data)}\0'.encode() + data, usedforsecurity=False)
        tree.append({'path': name, 'type': 'blob', 'mode': '100644', 'sha': blob.hexdigest()})

    def metadata(payload):
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(payload).encode()))

    def serve(request):
        requests.append(str(request.url))
        url = str(request.url)
        if url == f'{API}/commits/main':
            return metadata({'sha': REVISION, 'commit': {'tree': {'sha': TREE}}})
        if url == f'{API}/git/trees/{TREE}?recursive=1':
            return metadata({'sha': TREE, 'truncated': truncated, 'tree': tree})
        if url == f'{ARCHIVES}/{REVISION}':
            return httpx.Response(200, stream=httpx.ByteStream(contents.getvalue()))
        pytest.fail(f'Unexpected URL {url}')

    return httpx.MockTransport(serve)


def prepare(installation, transport, *, policy=None, publish=None, test_command=''):
    root, history = installation
    policy = policy or Policy()
    ticket = policy.ticket()
    return prepare_candidate(
        root, root, history, check=lambda: policy.check(ticket),
        publish=publish or (lambda operation: policy.run_if_current(ticket, operation)),
        transport=transport, test_command=test_command)


def test_preparing_a_revision_does_not_change_the_running_version(installation):
    root, history = installation
    candidate = prepare(installation, fake_github([]))
    assert candidate.revision == REVISION
    # The version that runs is untouched, and no release was selected.
    assert read_state(root)['active'] == 'base'
    assert read_state(root).get('previous') is None
    assert (root / 'main.py').read_bytes() == b'original code'
    # The prepared revision is recorded, with the files it changes.
    stored = read_candidate(root)
    assert stored is not None and stored.revision == REVISION
    assert 'main.py' in stored.changed
    # No history was touched, because nothing was applied.
    assert not list(history.parent.glob('history-before-update-*.sqlite3'))


def test_approving_a_revision_selects_it_and_keeps_the_previous_one(installation, monkeypatch):
    root, history = installation
    monkeypatch.setattr('core.candidates.run_tests',
                        lambda folder, command, timeout=1800, cancel=None:
                        {'status': 'passed', 'summary': '3 passed', 'output': ''})
    candidate = prepare(installation, fake_github([]), test_command='pytest -q')
    approve_candidate(root, candidate)
    message = stage_candidate(root, history, candidate)
    assert 'staged' in message.lower() or 'Update staged' in message
    state = read_state(root)
    assert state['active'] == candidate.digest
    assert state['previous'] == 'base'
    assert state['last_source_revision'] == REVISION
    assert (release_path(root, state['active']) / 'main.py').read_bytes() == b'new code'
    # The history was backed up before the code changed.
    backup, = history.parent.glob('history-before-update-*.sqlite3')
    with sqlite3.connect(backup) as db:
        assert db.execute('SELECT message FROM history').fetchone() == ('retained',)
    # And the previous version can be selected again.
    rollback(root)
    assert read_state(root)['active'] == 'base'


def test_a_revision_whose_tests_failed_cannot_be_applied(installation, monkeypatch):
    root, history = installation
    monkeypatch.setattr('core.candidates.run_tests',
                        lambda folder, command, timeout=1800, cancel=None:
                        {'status': 'failed', 'summary': '1 failed', 'output': 'boom'})
    candidate = prepare(installation, fake_github([]), test_command='pytest -q')
    assert candidate.tests['status'] == 'failed'
    assert candidate.appliable is False
    with pytest.raises(UpdateError, match='tests'):
        approve_candidate(root, candidate)
    with pytest.raises(UpdateError, match='tests'):
        stage_candidate(root, history, candidate)
    assert read_state(root)['active'] == 'base'


def test_a_prepared_revision_that_changed_after_the_review_cannot_be_applied(
        installation, monkeypatch):
    root, history = installation
    monkeypatch.setattr('core.candidates.run_tests',
                        lambda folder, command, timeout=1800, cancel=None:
                        {'status': 'passed', 'summary': '3 passed', 'output': ''})
    candidate = prepare(installation, fake_github([]), test_command='pytest -q')
    approve_candidate(root, candidate)
    # The prepared files are changed after the owner looked at them.
    from core.candidates import prepared_path
    target = prepared_path(root, candidate.revision) / 'main.py'
    target.write_bytes(b'something else')
    with pytest.raises(UpdateError, match='changed after the review'):
        stage_candidate(root, history, candidate)
    assert read_state(root)['active'] == 'base'


def test_only_the_approved_revision_is_activated(installation, monkeypatch):
    """A revision that was prepared but not approved never runs."""
    root, history = installation
    monkeypatch.setattr('core.candidates.run_tests',
                        lambda folder, command, timeout=1800, cancel=None:
                        {'status': 'passed', 'summary': '3 passed', 'output': ''})
    approved = prepare(installation, fake_github([]), test_command='pytest -q')
    approve_candidate(root, approved)
    # Another revision is prepared afterwards. It was never approved.
    other = Candidate(revision='d' * 40, digest='e' * 64, base=approved.base,
                      changed=('main.py',), tests={'status': 'passed', 'summary': '3 passed'})
    write_candidate(root, other)
    with pytest.raises(UpdateError, match='must be current'):
        stage_candidate(root, history, approved)
    assert read_state(root)['active'] == 'base'
    assert read_candidate(root) == other
    write_candidate(root, approved)
    stage_candidate(root, history, approved)
    assert read_state(root)['active'] == approved.digest
    assert read_candidate(root) is None


def test_a_rejected_revision_leaves_the_running_version_alone(installation):
    root, history = installation
    candidate = prepare(installation, fake_github([]))
    message = reject_candidate(root, candidate)
    assert 'rejected' in message
    assert read_candidate(root) is None
    assert read_state(root)['active'] == 'base'


def test_tampered_source_is_rejected_before_anything_is_written(installation):
    root, history = installation
    transport = fake_github([], archive_files=dict(FILES, **{'main.py': b'altered code'}))
    with pytest.raises(UpdateError, match='commit verification'):
        prepare(installation, transport)
    assert read_state(root)['active'] == 'base'
    assert read_candidate(root) is None
    assert not list(history.parent.glob('history-before-update-*.sqlite3'))


def test_truncated_manifest_is_rejected(installation):
    with pytest.raises(UpdateError, match='complete source tree'):
        prepare(installation, fake_github([], truncated=True))


def test_dependency_changes_are_rejected(installation):
    root, history = installation
    transport = fake_github([], files=dict(FILES, **{'requirements.txt': b'different==2'}))
    with pytest.raises(UpdateError, match='Dependencies changed'):
        prepare(installation, transport)
    assert read_state(root)['active'] == 'base'


def test_emergency_stop_prevents_the_preparation(installation):
    root, _ = installation
    policy = Policy()
    ticket = policy.ticket()

    def stop_before_publish(operation):
        policy.stop()
        policy.run_if_current(ticket, operation)

    with pytest.raises(Stopped):
        prepare(installation, fake_github([]), policy=policy, publish=stop_before_publish)
    assert read_state(root)['active'] == 'base'


def test_the_prepared_files_are_verified_by_their_own_digest(installation):
    root, _ = installation
    candidate = prepare(installation, fake_github([]))
    from core.candidates import prepared_files
    files = prepared_files(root, candidate.revision)
    assert content_digest(files) == candidate.digest
    assert files['main.py'] == b'new code'


def test_automatic_source_update_requires_opt_in_and_saves_choice(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from desktop.app import Window
    from security.policy import Denied

    app = QApplication.instance() or QApplication([])
    root = tmp_path / 'install'
    (root / 'scripts').mkdir(parents=True)
    (root / 'scripts' / 'launch.py').touch()
    monkeypatch.setenv('JARVIS_INSTALL_ROOT', str(root))
    data = tmp_path / 'user'
    window = Window(data)
    checker = window.release_checker
    checks = []
    monkeypatch.setattr(checker, 'start_source_worker', lambda: checks.append('started'))
    assert not checker.source_enabled
    checker.check_source_if_due()
    assert checks == []
    window.confirm = lambda action: False
    with pytest.raises(Denied):
        checker.set_source_enabled(True)
    assert not checker.source_enabled
    window.confirm = lambda action: True
    checker.set_source_enabled(True)
    assert checks == ['started']
    window.close()

    reopened = Window(data)
    assert reopened.release_checker.source_enabled
    reopened.release_checker.set_source_enabled(False)
    assert not reopened.release_checker.source_enabled
    reopened.close()


def test_background_fetch_does_not_execute_candidate(installation, monkeypatch):
    from core.candidates import test_candidate as run_candidate_test
    from desktop.background import SourceCheckWorker

    root, history = installation
    policy = Policy()
    ticket = policy.ticket()
    ran = []
    calls = []

    def prepare_without_network(*args, **kwargs):
        return prepare(installation, fake_github([]), test_command=kwargs.get('test_command', ''))

    def run_tests(folder, command, **kwargs):
        ran.append(command)
        return {'status': 'passed', 'summary': 'passed', 'output': ''}

    monkeypatch.setattr('desktop.background.prepare_candidate', prepare_without_network)
    monkeypatch.setattr('core.candidates.run_tests', run_tests)
    auto = SourceCheckWorker(root, root, history, policy, ticket, 'pytest -q')
    auto.prepared.connect(calls.append)
    auto.run()
    candidate, = calls
    assert not ran
    assert not candidate.appliable
    assert read_state(root)['active'] == 'base'

    tested = run_candidate_test(root, candidate, 'pytest -q', check=lambda: None,
                                publish=lambda operation: operation())
    assert ran == ['pytest -q']
    assert tested.appliable
    assert read_state(root)['active'] == 'base'
