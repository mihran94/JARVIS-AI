"""The history backup: what it writes, what it protects and what it refuses.

WHAT IS COVERED
    * A backup is a consistent copy of the live database, sealed, and
      readable afterwards.
    * The plain text of a conversation never appears in the archive.
    * The right passphrase opens it and the wrong one does not.
    * A restore puts the messages and the notes back.
    * A restore keeps the database it replaced.
    * A restore refuses to overwrite a live database without being told
      to, and refuses a damaged or changed archive.
    * The header can be read without the passphrase, so the owner can
      see what a backup holds before opening it.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import sqlite3

import pytest

from memory.windows_backup import (
    BackupError, BackupLocked, create_backup, inspect_backup, restore_backup,
    seal, unseal, verify_backup,
)


def make_history(path, messages=3, notes=2):
    """A small history database with the shape the application uses."""
    db = sqlite3.connect(str(path))
    db.executescript('''
        CREATE TABLE messages(id INTEGER PRIMARY KEY, session TEXT, role TEXT, content TEXT);
        CREATE TABLE memories(id TEXT PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP,
            title TEXT, body TEXT, tags TEXT);
        CREATE TABLE config(key TEXT PRIMARY KEY, value TEXT);
        PRAGMA user_version=3;
    ''')
    for index in range(messages):
        db.execute('INSERT INTO messages(session, role, content) VALUES (?,?,?)',
                   ('session', 'user', f'Tamil secret message {index} வணக்கம்'))
    for index in range(notes):
        db.execute('INSERT INTO memories(id, title, body, tags) VALUES (?,?,?,?)',
                   (f'id{index}', f'Note {index}', 'The launch is on Friday.', 'work'))
    db.commit()
    db.close()
    return path


@pytest.fixture
def history(tmp_path):
    return make_history(tmp_path / 'history.sqlite3')


def test_a_backup_is_written_and_describes_itself(history, tmp_path):
    target = tmp_path / 'backup.jarvisbak'
    result = create_backup(history, target, passphrase='correct horse battery staple')
    assert target.is_file()
    header = inspect_backup(target)
    assert header.source == 'history.sqlite3'
    assert header.schema_version == 3
    assert header.message_count == 3
    assert header.note_count == 2
    assert header.sealed_with_windows_key is False
    assert result.encrypted is True
    assert result.sha256


def test_the_plain_text_never_appears_in_the_archive(history, tmp_path):
    target = tmp_path / 'backup.jarvisbak'
    create_backup(history, target, passphrase='a passphrase')
    raw = target.read_bytes()
    assert 'Tamil secret message' not in raw.decode('latin-1')
    assert 'வணக்கம்'.encode('utf-8') not in raw


def test_the_right_passphrase_opens_the_backup(history, tmp_path):
    target = tmp_path / 'backup.jarvisbak'
    create_backup(history, target, passphrase='a passphrase')
    header = verify_backup(target, passphrase='a passphrase')
    assert header.message_count == 3


def test_the_wrong_passphrase_is_refused(history, tmp_path):
    target = tmp_path / 'backup.jarvisbak'
    create_backup(history, target, passphrase='a passphrase')
    with pytest.raises(BackupLocked):
        verify_backup(target, passphrase='not the passphrase')


def test_a_backup_needs_a_passphrase(history, tmp_path):
    with pytest.raises(BackupError):
        create_backup(history, tmp_path / 'backup.jarvisbak')


def test_a_backup_will_not_overwrite_an_existing_file(history, tmp_path):
    target = tmp_path / 'backup.jarvisbak'
    target.write_text('mine', encoding='utf-8')
    with pytest.raises(BackupError):
        create_backup(history, target, passphrase='a passphrase')


def test_a_missing_database_is_refused(tmp_path):
    with pytest.raises(BackupError):
        create_backup(tmp_path / 'nothing.sqlite3', tmp_path / 'backup.jarvisbak',
                      passphrase='a passphrase')


def test_a_restore_puts_the_messages_and_the_notes_back(history, tmp_path):
    target = tmp_path / 'backup.jarvisbak'
    create_backup(history, target, passphrase='a passphrase')
    destination = tmp_path / 'restored.sqlite3'
    result = restore_backup(target, destination, passphrase='a passphrase')
    assert result.replaced is True
    db = sqlite3.connect(str(destination))
    try:
        assert db.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 3
        assert db.execute('SELECT COUNT(*) FROM memories').fetchone()[0] == 2
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
    finally:
        db.close()


def test_a_restore_keeps_the_database_it_replaced(history, tmp_path):
    target = tmp_path / 'backup.jarvisbak'
    create_backup(history, target, passphrase='a passphrase')
    live = tmp_path / 'live.sqlite3'
    live.write_bytes(b'a different database')
    result = restore_backup(target, live, passphrase='a passphrase', overwrite=True)
    assert result.previous_copy is not None
    assert result.previous_copy.is_file()
    assert result.previous_copy.read_bytes() == b'a different database'


def test_a_restore_refuses_to_overwrite_without_being_told_to(history, tmp_path):
    target = tmp_path / 'backup.jarvisbak'
    create_backup(history, target, passphrase='a passphrase')
    live = tmp_path / 'live.sqlite3'
    live.write_bytes(b'a different database')
    with pytest.raises(BackupError):
        restore_backup(target, live, passphrase='a passphrase')


def test_a_changed_archive_is_refused(history, tmp_path):
    target = tmp_path / 'backup.jarvisbak'
    create_backup(history, target, passphrase='a passphrase')
    raw = bytearray(target.read_bytes())
    raw[-20] ^= 0xFF
    target.write_bytes(bytes(raw))
    with pytest.raises(BackupLocked):
        verify_backup(target, passphrase='a passphrase')


def test_a_file_that_is_not_a_backup_is_refused(tmp_path):
    other = tmp_path / 'notes.txt'
    other.write_text('this is not a backup', encoding='utf-8')
    with pytest.raises(BackupError):
        inspect_backup(other)


def test_the_seal_detects_a_changed_payload():
    from memory.windows_backup import derive_key
    key = derive_key('passphrase', b'0123456789abcdef')
    nonce = b'0123456789abcdef'
    sealed = seal(b'hello there', key, nonce)
    assert unseal(sealed, key, nonce) == b'hello there'
    with pytest.raises(BackupLocked):
        unseal(sealed[:-1] + bytes([sealed[-1] ^ 0x01]), key, nonce)


def test_a_backup_of_an_empty_database_still_works(tmp_path):
    empty = tmp_path / 'history.sqlite3'
    sqlite3.connect(str(empty)).close()
    target = tmp_path / 'backup.jarvisbak'
    create_backup(empty, target, passphrase='a passphrase')
    header = inspect_backup(target)
    assert header.message_count == 0
