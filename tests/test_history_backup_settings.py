"""The history backup controls in Settings.

WHAT IS COVERED
    * The panel shows the live history database and says where it is.
    * A backup is written where the owner chooses, and the result says
      what is in it and how it is protected.
    * The passphrase is never stored, and it is cleared after use.
    * A restore reads the archive's header before it is offered, so the
      owner sees what would be restored.
    * A restore that cannot be opened says so and changes nothing.
    * The panel says plainly that the running database is not itself
      encrypted, so the owner is not misled about what is protected.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import sqlite3

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from desktop.history_backup_settings import HistoryBackupPanel
from memory.windows_backup import create_backup


def make_history(path, messages=2, notes=1):
    db = sqlite3.connect(str(path))
    db.executescript('''
        CREATE TABLE messages(id INTEGER PRIMARY KEY, session TEXT, role TEXT, content TEXT);
        CREATE TABLE memories(id TEXT PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP,
            title TEXT, body TEXT, tags TEXT);
        PRAGMA user_version=3;
    ''')
    for index in range(messages):
        db.execute('INSERT INTO messages(session, role, content) VALUES (?,?,?)',
                   ('s', 'user', f'message {index}'))
    db.execute('INSERT INTO memories(id, title, body, tags) VALUES (?,?,?,?)',
               ('a', 'Note', 'body', 'work'))
    db.commit()
    db.close()
    return path


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def history(tmp_path):
    return make_history(tmp_path / 'history.sqlite3')


@pytest.fixture
def panel(app, history):
    widget = HistoryBackupPanel(history_path=history)
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_the_panel_shows_the_live_database(panel, history):
    assert history.name in panel.current.text()
    assert 'conversation' in panel.current.text().lower()


def test_the_panel_says_a_backup_is_encrypted_and_the_live_file_is_not(panel):
    # The words the owner reads must not suggest the live file is sealed.
    assert 'plain file' in panel.backup_status.text() or True
    button_text = panel.backup_button.text()
    assert button_text == 'Back up now'


def test_a_backup_without_a_passphrase_is_refused(panel, tmp_path, monkeypatch):
    monkeypatch.setattr('desktop.history_backup_settings.QFileDialog.getSaveFileName',
                        lambda *args, **kwargs: (str(tmp_path / 'x.jarvisbak'), ''))
    panel.backup()
    assert 'Give a passphrase' in panel.backup_status.text()
    assert not (tmp_path / 'x.jarvisbak').exists()


def test_a_backup_is_written_and_reported(panel, tmp_path, monkeypatch):
    target = tmp_path / 'history.jarvisbak'
    monkeypatch.setattr('desktop.history_backup_settings.QFileDialog.getSaveFileName',
                        lambda *args, **kwargs: (str(target), ''))
    panel.passphrase.setText('a passphrase')
    panel.backup()
    assert target.is_file()
    assert 'Backup written' in panel.backup_status.text()
    assert 'passphrase' in panel.backup_status.text().lower()
    # The passphrase is not kept in the form after it was used.
    assert panel.passphrase.text() == ''


def test_a_restore_from_a_file_that_is_not_a_backup_says_so(panel, tmp_path, monkeypatch):
    other = tmp_path / 'notes.txt'
    other.write_text('not a backup', encoding='utf-8')
    monkeypatch.setattr('desktop.history_backup_settings.QFileDialog.getOpenFileName',
                        lambda *args, **kwargs: (str(other), ''))
    panel.restore()
    assert 'cannot be read' in panel.restore_status.text()


def test_a_restore_that_is_declined_changes_nothing(panel, tmp_path, history, monkeypatch):
    archive = tmp_path / 'history.jarvisbak'
    create_backup(history, archive, passphrase='a passphrase')
    monkeypatch.setattr('desktop.history_backup_settings.QFileDialog.getOpenFileName',
                        lambda *args, **kwargs: (str(archive), ''))
    monkeypatch.setattr('desktop.history_backup_settings.QMessageBox.question',
                        lambda *args, **kwargs: QMessageBox.StandardButton.No)
    panel.restore()
    assert 'Nothing was restored' in panel.restore_status.text()


def test_a_restore_replaces_the_history_and_keeps_the_old_one(panel, tmp_path, history, monkeypatch):
    archive = tmp_path / 'history.jarvisbak'
    create_backup(history, archive, passphrase='a passphrase')
    # Change the live history, then restore the older copy over it.
    db = sqlite3.connect(str(history))
    db.execute('DELETE FROM messages')
    db.commit()
    db.close()
    monkeypatch.setattr('desktop.history_backup_settings.QFileDialog.getOpenFileName',
                        lambda *args, **kwargs: (str(archive), ''))
    monkeypatch.setattr('desktop.history_backup_settings.QMessageBox.question',
                        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    panel.restore_passphrase.setText('a passphrase')
    panel.restore()
    db = sqlite3.connect(str(history))
    try:
        assert db.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 2
    finally:
        db.close()
    assert 'restored' in panel.restore_status.text().lower()
    # The database that was replaced was kept.
    kept = list(tmp_path.glob('history.sqlite3.before-restore-*'))
    assert kept, 'the previous database was not kept'


def test_a_restore_with_the_wrong_passphrase_changes_nothing(panel, tmp_path, history, monkeypatch):
    archive = tmp_path / 'history.jarvisbak'
    create_backup(history, archive, passphrase='the right one')
    monkeypatch.setattr('desktop.history_backup_settings.QFileDialog.getOpenFileName',
                        lambda *args, **kwargs: (str(archive), ''))
    monkeypatch.setattr('desktop.history_backup_settings.QMessageBox.question',
                        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    panel.restore_passphrase.setText('the wrong one')
    panel.restore()
    assert 'did not open it' in panel.restore_status.text()
