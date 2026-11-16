import hashlib
from io import BytesIO
import json
import sqlite3
import zipfile

import httpx
import pytest

from core.source_updates import API, ARCHIVES, stage_latest
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


def stage(installation, transport, *, policy=None, publish=None):
    root, history = installation
    policy = policy or Policy()
    ticket = policy.ticket()
    return stage_latest(root, root, history, check=lambda: policy.check(ticket),
                        publish=publish or (lambda operation: policy.run_if_current(ticket, operation)),
                        transport=transport)


def test_verified_source_stages_preserves_data_and_does_not_reapply_on_rollback(installation):
    root, history = installation
    requests = []
    archive_files = dict(FILES, **{'START_JARVIS.cmd': b'@echo off\r\nexit /b 0\r\n'})
    transport = fake_github(requests, archive_files=archive_files)
    assert 'staged' in stage(installation, transport)
    state = read_state(root)
    assert state['previous'] == 'base'
    assert state['last_source_revision'] == REVISION
    assert (release_path(root, state['active']) / 'main.py').read_bytes() == b'new code'
    assert (root / 'main.py').read_bytes() == b'original code'
    backup, = history.parent.glob('history-before-update-*.sqlite3')
    with sqlite3.connect(backup) as db:
        assert db.execute('SELECT message FROM history').fetchone() == ('retained',)
    requests.clear()
    assert 'already selected' in stage(installation, transport)
    assert requests == []
    rollback(root)
    assert 'already been checked' in stage(installation, transport)
    assert requests == [f'{API}/commits/main']
    assert read_state(root)['active'] == 'base'


def test_tampered_source_is_rejected_before_backup(installation):
    root, history = installation
    transport = fake_github([], archive_files=dict(FILES, **{'main.py': b'altered code'}))
    with pytest.raises(UpdateError, match='commit verification'):
        stage(installation, transport)
    assert read_state(root)['active'] == 'base'
    assert not list(history.parent.glob('history-before-update-*.sqlite3'))


def test_truncated_manifest_is_rejected(installation):
    with pytest.raises(UpdateError, match='complete source tree'):
        stage(installation, fake_github([], truncated=True))


def test_dependency_changes_are_rejected(installation):
    root, history = installation
    transport = fake_github([], files=dict(FILES, **{'requirements.txt': b'different==2'}))
    with pytest.raises(UpdateError, match='Dependencies changed'):
        stage(installation, transport)
    assert read_state(root)['active'] == 'base'
    assert not list(history.parent.glob('history-before-update-*.sqlite3'))


def test_emergency_stop_prevents_selection(installation):
    root, _ = installation
    policy = Policy()
    ticket = policy.ticket()

    def stop_before_publish(operation):
        policy.stop()
        policy.run_if_current(ticket, operation)

    with pytest.raises(Stopped):
        stage(installation, fake_github([]), policy=policy, publish=stop_before_publish)
    assert read_state(root)['active'] == 'base'


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
