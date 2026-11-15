"""Check for published releases and stage an explicitly approved source update."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid
from PySide6.QtWidgets import QCheckBox, QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog, QPlainTextEdit
from PySide6.QtCore import QObject, QTimer, Qt, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from core.updates import (installation_root, inspect_zip, changed_files, read_state,
                          release_path, activate_zip, rollback)
from security.policy import Action, Stopped


class ReleaseChecker(QObject):
    status_changed = Signal(str)
    PERIOD = 24 * 60 * 60

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.store = window.store
        self.network = QNetworkAccessManager(self)
        self.reply = None
        self.background = False
        self.status = self.store.get('release_check_status', '')
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_if_due)
        if self.enabled:
            self.timer.start(60_000)
            QTimer.singleShot(0, self.check_if_due)

    @property
    def enabled(self):
        return bool(self.store.get('daily_release_check', False))

    def set_enabled(self, enabled):
        self.store.set('daily_release_check', enabled)
        if enabled:
            self.timer.start(60_000)
            self.check_if_due()
        else:
            self.timer.stop()
            if self.reply is not None and self.background:
                self.reply.abort()

    def check_if_due(self):
        now = datetime.now(timezone.utc).timestamp()
        last = self.store.get('release_check_attempt', 0)
        if self.enabled and now - last >= self.PERIOD:
            self.check(background=True)

    def set_status(self, text):
        self.status = text
        self.status_changed.emit(text)

    def check(self, *, background=False):
        if self.reply is not None or self.window.policy.stopped:
            return
        ticket = self.window.policy.ticket()
        request = QNetworkRequest(QUrl('https://api.github.com/repos/mihran94/JARVIS-AI/releases/latest'))
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        request.setTransferTimeout(10000)
        self.store.set('release_check_attempt', datetime.now(timezone.utc).timestamp())
        reply = self.network.get(request)
        self.reply = reply
        self.background = background
        self.set_status('Checking GitHub…')

        def finished():
            try:
                self.window.policy.check(ticket)
                status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
                    message = 'Release check cancelled.'
                elif status == 404:
                    message = 'No published release was visible. Check Releases in your signed-in browser.'
                elif reply.error() != QNetworkReply.NetworkError.NoError or status != 200:
                    message = 'GitHub release check failed. Try the Releases link.'
                else:
                    payload = json.loads(bytes(reply.readAll()))
                    tag = payload.get('tag_name', '') if isinstance(payload, dict) else ''
                    if not isinstance(tag, str) or not tag.strip():
                        raise ValueError('Invalid release data')
                    tag = ' '.join(tag.split())[:100]
                    message = f'Latest published release: {tag}. Review it through the Releases link.'
                    if tag != self.store.get('last_visible_release'):
                        self.store.set('last_visible_release', tag)
                        self.window.statusBar().showMessage(f'GitHub release {tag} is available to review.', 15000)
            except Stopped:
                message = 'Release check cancelled.'
            except ValueError:
                message = 'GitHub returned invalid release information.'
            finally:
                self.reply = None
                reply.deleteLater()
            self.store.set('release_check_status', message)
            self.set_status(message)

        reply.finished.connect(finished)


def open_updates(window):
    dialog = QDialog(window)
    dialog.setWindowTitle('Review a JARVIS source update')
    dialog.resize(760, 550)
    layout = QVBoxLayout(dialog)
    note = QLabel('Download the source ZIP from your trusted GitHub repository, then select it here. '
                  'ZIP hashes detect changes after review; they do NOT prove publisher identity. '
                  'Close and restart JARVIS after applying. Original code is retained.')
    note.setWordWrap(True)
    layout.addWidget(note)
    download = QLabel(
        '<a href="https://github.com/mihran94/JARVIS-AI/releases">Open JARVIS releases</a>'
    )
    download.setOpenExternalLinks(True)
    layout.addWidget(download)
    report = QPlainTextEdit()
    report.setReadOnly(True)
    layout.addWidget(report)
    check = QPushButton('Check for a published release')
    checker = window.release_checker
    automatic = QCheckBox('Check GitHub once a day while JARVIS is open')
    automatic.setChecked(checker.enabled)
    automatic.toggled.connect(checker.set_enabled)
    release_status = QLabel(checker.status)
    release_status.setTextFormat(Qt.TextFormat.PlainText)
    release_status.setWordWrap(True)
    layout.addWidget(automatic)
    layout.addWidget(check)
    layout.addWidget(release_status)
    checker.status_changed.connect(release_status.setText)
    select = QPushButton('Select GitHub ZIP')
    apply = QPushButton('Approve selected update for next startup')
    apply.setEnabled(False)
    undo = QPushButton('Select previous code version (rollback)')
    for button in (select, apply, undo): layout.addWidget(button)
    reviewed = {}
    root = installation_root()

    def choose():
        filename, _ = QFileDialog.getOpenFileName(dialog, 'Select trusted source ZIP', '', 'ZIP archives (*.zip)')
        if not filename: return
        reviewed.clear(); apply.setEnabled(False)
        def operation():
            window.policy.ticket()
            digest, files = inspect_zip(filename)
            current = release_path(root, read_state(root)['active'])
            changes = changed_files(current, files)
            sensitive = [n for n in changes if n.startswith(('security/', 'agents/', 'core/', 'desktop/', 'scripts/'))]
            report.setPlainText('SHA-256: ' + digest + '\n\nChanged/new files:\n' + '\n'.join(changes) +
                                '\n\nSecurity, orchestration, UI or update code changed:\n' + '\n'.join(sensitive) +
                                '\n\nThis replaces the source snapshot, including removed files. '
                                'Inspect the ZIP/source diff in GitHub before approval. '
                                'Permissions and update code may change. Only approve a source you trust. '
                                'Dependencies and database code must match this installation.')
            reviewed.update(path=filename, digest=digest)
            apply.setEnabled(True)
        window.notify(operation)

    def install():
        if not reviewed: return
        def operation():
            if window.worker is not None:
                raise ValueError('Wait for the current request to finish before updating.')
            action = Action('activate_reviewed_source_update', 'Includes any listed permission/update changes', reviewed['digest'])
            def activate():
                # Consistent SQLite backup, separate from the install tree and never sent anywhere.
                backup = Path(window.store.path).parent / ('history-before-update-' + uuid.uuid4().hex + '.sqlite3')
                with sqlite3.connect(window.store.path) as source, sqlite3.connect(backup) as target:
                    source.backup(target)
                return activate_zip(root, reviewed['path'], reviewed['digest'])
            result = window.gateway.run(action, window.confirm, activate)
            report.appendPlainText('\n' + result)
            apply.setEnabled(False)
        window.notify(operation)

    def restore():
        def operation():
            if window.worker is not None:
                raise ValueError('Wait for the current request to finish before rollback.')
            result = window.gateway.run(Action('rollback_code', 'Select previous version; data remains unchanged'),
                                        window.confirm, lambda: rollback(root))
            report.appendPlainText('\n' + result)
        window.notify(operation)
    check.clicked.connect(lambda: checker.check())
    select.clicked.connect(choose)
    apply.clicked.connect(install)
    undo.clicked.connect(restore)
    dialog.exec()
    dialog.deleteLater()
