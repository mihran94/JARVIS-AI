"""The history backup controls in Settings.

WHAT THIS IS
    The owner's conversations, the saved notes and the task history live
    in one file, `history.sqlite3`. This panel is where the owner backs
    that file up, sees what a backup holds, and restores one.

    The panel says plainly what is protected and what is not:

    * the running database is a plain file, exactly as it has always
      been, so the application opens it in milliseconds. This is not
      encryption of the live records;
    * a *backup* is encrypted. On Windows the key is held by the
      Windows account that made it, so it opens without a passphrase
      and nobody else can open it. On other systems a passphrase is
      used, and it is never stored.

WHAT THIS IS NOT
    * It does not back up to the internet. Nothing leaves the computer.
    * It does not restore without asking. A restore replaces live
      history, so it goes through the same one-use approval as every
      other consequential action, and the previous database is kept.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from memory.windows_backup import (
    BackupError, BackupLocked, create_backup, inspect_backup, restore_backup,
    windows_available,
)

#: The extension the backup files use.
BACKUP_FILTER = 'JARVIS backup (*.jarvisbak);;All files (*)'

#: The passphrase placeholder. It is never stored.
PASSPHRASE_PLACEHOLDER = 'Not stored. Needed to restore this backup.'


class HistoryBackupPanel(QWidget):
    """Back up and restore the live history database."""

    def __init__(self, *, history_path, parent=None):
        super().__init__(parent)
        self.history_path = Path(history_path)
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        note = QLabel(
            'Your conversations, saved notes and task history live in one local '
            'database. The running database is a plain file, so the application '
            'opens it quickly. A backup of it is encrypted.')
        note.setWordWrap(True)
        layout.addWidget(note)

        backup_box = QGroupBox('Back up the history')
        backup_layout = QFormLayout(backup_box)
        self.current = QLabel('')
        self.current.setWordWrap(True)
        self.current.setAccessibleName('The current history database')
        backup_layout.addRow('Database', self.current)

        self.passphrase = QLineEdit()
        self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase.setPlaceholderText(
            'A passphrase for this backup' if not windows_available()
            else 'Optional: use a passphrase instead of the Windows key')
        self.passphrase.setAccessibleName('Backup passphrase')
        backup_layout.addRow('Passphrase', self.passphrase)

        row = QHBoxLayout()
        self.backup_button = QPushButton('Back up now')
        self.backup_button.clicked.connect(self.backup)
        row.addWidget(self.backup_button)
        self.windows_key_button = QPushButton('Back up with the Windows key')
        self.windows_key_button.clicked.connect(self.backup_with_windows_key)
        self.windows_key_button.setVisible(windows_available())
        self.windows_key_button.setToolTip(
            'The key is held by this Windows account, so the backup opens here '
            'without a passphrase and cannot be opened by anyone else.')
        row.addWidget(self.windows_key_button)
        backup_layout.addRow(row)

        self.backup_status = QLabel('')
        self.backup_status.setWordWrap(True)
        self.backup_status.setTextFormat(Qt.TextFormat.PlainText)
        self.backup_status.setAccessibleName('Backup result')
        backup_layout.addRow('Result', self.backup_status)
        layout.addWidget(backup_box)

        restore_box = QGroupBox('Restore a backup')
        restore_layout = QFormLayout(restore_box)
        self.restore_passphrase = QLineEdit()
        self.restore_passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.restore_passphrase.setPlaceholderText('The passphrase this backup was made with')
        self.restore_passphrase.setAccessibleName('Restore passphrase')
        restore_layout.addRow('Passphrase', self.restore_passphrase)
        row = QHBoxLayout()
        self.restore_button = QPushButton('Restore from a backup file')
        self.restore_button.clicked.connect(self.restore)
        row.addWidget(self.restore_button)
        restore_layout.addRow(row)
        self.restore_status = QLabel('')
        self.restore_status.setWordWrap(True)
        self.restore_status.setTextFormat(Qt.TextFormat.PlainText)
        self.restore_status.setAccessibleName('Restore result')
        restore_layout.addRow('Result', self.restore_status)
        layout.addWidget(restore_box)

        layout.addStretch(1)

    # ------------------------------------------------------------------ state

    def refresh(self):
        """Show the live database and what a backup would hold."""
        if not self.history_path.exists():
            self.current.setText('There is no history database yet. It is made when '
                                 'you first talk to JARVIS.')
            return
        try:
            size = self.history_path.stat().st_size
        except OSError:
            size = 0
        self.current.setText(f'{self.history_path.name} · {size:,} bytes · '
                             'conversations, notes, task history and usage')

    # ------------------------------------------------------------------ backup

    def backup(self):
        """Write an encrypted backup where the owner chooses."""
        passphrase = self.passphrase.text()
        if not passphrase:
            self.backup_status.setText('Give a passphrase for this backup, or use the '
                                        'Windows key.')
            return
        self._write_backup(passphrase=passphrase, windows_key=False)

    def backup_with_windows_key(self):
        """Write an encrypted backup that this Windows account alone can open."""
        self._write_backup(passphrase='', windows_key=True)

    def _write_backup(self, *, passphrase: str, windows_key: bool):
        suggested = str(self.history_path.with_name(
            f'jarvis-history-{self.history_path.parent.name}.jarvisbak'))
        path, _ = QFileDialog.getSaveFileName(self, 'Save the history backup', suggested,
                                               BACKUP_FILTER)
        if not path:
            return
        if not path.endswith('.jarvisbak'):
            path += '.jarvisbak'
        try:
            result = create_backup(self.history_path, Path(path), passphrase=passphrase,
                                   windows_key=windows_key)
        except BackupError as error:
            self.backup_status.setText(f'The backup was not made. {error}')
            return
        except OSError as error:
            self.backup_status.setText(f'The backup file could not be written. {error}')
            return
        self.passphrase.clear()
        self.backup_status.setText(
            f'Backup written to {result.path.name} · {result.bytes:,} bytes · '
            f'{result.message_count} message(s) and {result.note_count} note(s). '
            f'{result.message}')
        self.refresh()

    # ----------------------------------------------------------------- restore

    def restore(self):
        """Restore a backup over the live history, after the owner agrees."""
        path, _ = QFileDialog.getOpenFileName(self, 'Choose a history backup', '',
                                              BACKUP_FILTER)
        if not path:
            return
        try:
            header = inspect_backup(path)
        except BackupError as error:
            self.restore_status.setText(f'That file cannot be read. {error}')
            return
        detail = (f'Made {header.created}\n'
                  f'{header.message_count} message(s) and {header.note_count} note(s)\n'
                  f'{header.plain_bytes:,} bytes of history')
        if header.sealed_with_windows_key:
            detail += '\nSealed with this Windows account.'
        answer = QMessageBox.question(
            self, 'Restore this history?',
            f'{detail}\n\nThe live history will be replaced. The database it replaces '
            'is kept beside it, so nothing is lost.\n\nRestore this backup?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            self.restore_status.setText('Nothing was restored.')
            return
        passphrase = self.restore_passphrase.text()
        try:
            result = restore_backup(path, self.history_path, passphrase=passphrase,
                                    keep_previous=True, overwrite=True)
        except BackupLocked:
            self.restore_status.setText('That backup needs its passphrase, and the one '
                                        'given did not open it. Nothing was restored.')
            return
        except BackupError as error:
            self.restore_status.setText(f'The history was not restored. {error}')
            return
        except OSError as error:
            self.restore_status.setText(f'The history was not restored. {error}')
            return
        self.restore_passphrase.clear()
        self.restore_status.setText(result.message)
        self.refresh()


__all__ = ['BACKUP_FILTER', 'PASSPHRASE_PLACEHOLDER', 'HistoryBackupPanel']
