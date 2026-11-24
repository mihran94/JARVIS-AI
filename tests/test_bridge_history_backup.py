"""The history backup the phone may ask the PC for.

WHAT IS COVERED
    * The phone's backup request is recognised, and an unknown action is
      not.
    * A restore may only name a plain backup file. A phone can never
      point the restore at a path of its own choosing.
    * When the owner approves, the backup is really made, and the job
      reports the name, the size and the checksum of what was written.
    * The history itself is never sent back to the phone.
    * A declined approval changes nothing, and the job is rejected.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import json
import sqlite3

import pytest
from PySide6.QtWidgets import QApplication

from desktop.bridge_panel import BridgePanel
from remote.jobs import (
    HISTORY_BACKUP_ACTION, HISTORY_RESTORE_ACTION, JobStore,
)


def make_history(path):
    """A small history database."""
    db = sqlite3.connect(str(path))
    db.executescript('''
        CREATE TABLE messages(id INTEGER PRIMARY KEY, session TEXT, role TEXT, content TEXT);
        CREATE TABLE memories(id TEXT PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP,
            title TEXT, body TEXT, tags TEXT);
        PRAGMA user_version=3;
    ''')
    db.execute('INSERT INTO messages(session, role, content) VALUES (?,?,?)',
               ('s', 'user', 'a private conversation'))
    db.commit()
    db.close()
    return path


@pytest.fixture
def history(tmp_path):
    return make_history(tmp_path / 'history.sqlite3')


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def select_job(panel, job_id):
    """Put the row of this job under the cursor."""
    for row in range(panel.jobs.rowCount()):
        item = panel.jobs.item(row, 0)
        if item is not None and item.text() == job_id:
            panel.jobs.selectRow(row)
            return True
    return False


def make_panel(tmp_path, history, *, confirm=None, errors=None, passphrase='test-passphrase'):
    """A bridge panel with a history to back up."""
    from core.store import Store
    from security.policy import Policy
    from security.vault import Vault

    store = Store(tmp_path / 'bridge.sqlite3')
    errors = errors if errors is not None else []

    def notify(operation):
        try:
            operation()
        except Exception as error:
            errors.append(str(error))

    panel = BridgePanel(Policy(), store, Vault(), confirm or (lambda action: True),
                        notify, history_path=history, history_passphrase=passphrase)
    panel.errors = errors
    return panel


# ── what the phone may ask for ─────────────────────────────────────────────

def test_the_backup_action_is_recognised():
    jobs = JobStore()
    job = jobs.submit('CUSTOM', 'Back up the conversation history',
                      json.dumps({'action': HISTORY_BACKUP_ACTION}), True)
    assert job.operation == HISTORY_BACKUP_ACTION


def test_an_unknown_action_is_not_recognised():
    jobs = JobStore()
    job = jobs.submit('CUSTOM', 'Something else',
                      json.dumps({'action': 'delete_everything'}), True)
    assert job.operation is None


def test_a_restore_may_only_name_a_plain_backup_file():
    jobs = JobStore()
    good = jobs.submit('CUSTOM', 'Restore', json.dumps(
        {'action': HISTORY_RESTORE_ACTION, 'backup': 'phone-history-1.jarvisbak'}), True)
    # The name travels with the operation, because a job record keeps no
    # phone text at all.
    assert good.operation == f'{HISTORY_RESTORE_ACTION}:phone-history-1.jarvisbak'
    for name in ('../secrets.jarvisbak', 'folder/backup.jarvisbak',
                 'folder\\backup.jarvisbak', 'backup.txt', ''):
        job = jobs.submit('CUSTOM', 'Restore', json.dumps(
            {'action': HISTORY_RESTORE_ACTION, 'backup': name}), True)
        assert job.operation is None, name


# ── what the PC does ───────────────────────────────────────────────────────

def test_the_backup_is_really_made(app, tmp_path, history):
    panel = make_panel(tmp_path, history)
    try:
        jobs = panel.bridge.jobs
        job = jobs.submit('CUSTOM', 'Back up the conversation history',
                          json.dumps({'action': HISTORY_BACKUP_ACTION}), True)
        panel.refresh()
        assert select_job(panel, job.id)
        panel.approve_job()
        job = jobs.get(job.id)
        assert job.state == 'SUCCEEDED', job.error
        backups = list((tmp_path / 'backups').glob('*.jarvisbak'))
        assert len(backups) == 1
        assert backups[0].stat().st_size > 0
        # The phone is told what was made, and nothing of the history.
        assert backups[0].name in job.outputs[0]
        assert 'SHA-256' in job.outputs[0]
        assert 'private conversation' not in job.outputs[0]
    finally:
        panel.close()


def test_a_declined_backup_changes_nothing(app, tmp_path, history):
    panel = make_panel(tmp_path, history, confirm=lambda action: False)
    try:
        jobs = panel.bridge.jobs
        job = jobs.submit('CUSTOM', 'Back up the conversation history',
                          json.dumps({'action': HISTORY_BACKUP_ACTION}), True)
        panel.refresh()
        assert select_job(panel, job.id)
        panel.approve_job()
        job = jobs.get(job.id)
        assert not (tmp_path / 'backups').exists() or \
            not list((tmp_path / 'backups').glob('*.jarvisbak'))
        assert job.state in ('QUEUED', 'REJECTED', 'CANCELLED')
    finally:
        panel.close()


def test_a_backup_of_a_desktop_without_history_says_so(app, tmp_path):
    panel = make_panel(tmp_path, tmp_path / 'nothing.sqlite3')
    try:
        jobs = panel.bridge.jobs
        job = jobs.submit('CUSTOM', 'Back up the conversation history',
                          json.dumps({'action': HISTORY_BACKUP_ACTION}), True)
        panel.refresh()
        assert select_job(panel, job.id)
        panel.approve_job()
        job = jobs.get(job.id)
        assert job.state in ('FAILED', 'REJECTED')
        assert 'no history' in (job.error or '')
    finally:
        panel.close()


def test_a_restore_of_a_backup_that_is_not_there_says_so(app, tmp_path, history):
    panel = make_panel(tmp_path, history)
    try:
        jobs = panel.bridge.jobs
        job = jobs.submit('CUSTOM', 'Restore', json.dumps(
            {'action': HISTORY_RESTORE_ACTION, 'backup': 'missing.jarvisbak'}), True)
        panel.refresh()
        assert select_job(panel, job.id)
        panel.approve_job()
        job = jobs.get(job.id)
        assert job.state == 'FAILED'
        assert 'not there' in (job.error or '')
    finally:
        panel.close()


def test_a_restore_puts_the_history_back(app, tmp_path, history):
    panel = make_panel(tmp_path, history)
    try:
        jobs = panel.bridge.jobs
        backup_job = jobs.submit('CUSTOM', 'Back up the conversation history',
                                json.dumps({'action': HISTORY_BACKUP_ACTION}), True)
        panel.refresh()
        assert select_job(panel, backup_job.id)
        panel.approve_job()
        backup_job = jobs.get(backup_job.id)
        assert backup_job.state == 'SUCCEEDED', backup_job.error
        name = backup_job.outputs[0].split()[1]

        # The history is changed after the backup was taken.
        db = sqlite3.connect(str(history))
        db.execute('DELETE FROM messages')
        db.commit()
        db.close()

        restore_job = jobs.submit('CUSTOM', 'Restore', json.dumps(
            {'action': HISTORY_RESTORE_ACTION, 'backup': name}), True)
        panel.refresh()
        assert select_job(panel, restore_job.id)
        panel.approve_job()
        restore_job = jobs.get(restore_job.id)
        assert restore_job.state == 'SUCCEEDED', restore_job.error
        db = sqlite3.connect(str(history))
        try:
            assert db.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 1
        finally:
            db.close()
        # The database that was replaced was kept.
        kept = list(tmp_path.glob('history.sqlite3.before-restore-*'))
        assert kept, 'the previous database was not kept'
    finally:
        panel.close()
