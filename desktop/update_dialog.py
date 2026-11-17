"""Check for published releases and stage an explicitly approved source update."""
import json
from datetime import datetime, timezone
from pathlib import Path
import os
import sys
from PySide6.QtWidgets import QCheckBox, QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog, QPlainTextEdit
from PySide6.QtCore import QObject, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from core.updates import (installation_root, inspect_zip, changed_files, read_state,
                          release_path, activate_zip, backup_history, rollback, UpdateError)
from desktop.background import SourceCheckWorker
from security.policy import Action, Stopped


class ReleaseChecker(QObject):
    status_changed = Signal(str)
    source_status_changed = Signal(str)
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

        self.source_worker = None
        self.source_status = self.store.get('source_update_status', '')
        self.source_timer = QTimer(self)
        self.source_timer.timeout.connect(self.check_source_if_due)
        if self.source_enabled and self.source_supported and not self.window.paused:
            self.source_timer.start(60_000)
            QTimer.singleShot(0, self.check_source_if_due)

    @property
    def source_enabled(self):
        return bool(self.store.get('automatic_source_updates', False))

    @property
    def source_supported(self):
        return (not getattr(sys, 'frozen', False) and 'JARVIS_INSTALL_ROOT' in os.environ
                and (installation_root() / 'scripts' / 'launch.py').is_file())

    def set_source_enabled(self, enabled):
        if not enabled:
            self.store.set('automatic_source_updates', False)
            self.source_timer.stop()
            self.cancel_source()
            return
        if not self.source_supported:
            return
        action = Action('Enable automatic source updates',
                        'Prepare future code from mihran94/JARVIS-AI main for your review. '
                        'Nothing is used until you approve that exact revision.')
        self.window.gateway.run(action, self.window.confirm,
                                lambda: self.store.set('automatic_source_updates', True))
        self.source_timer.start(60_000)
        self.check_source()

    def check_source_if_due(self):
        now = datetime.now(timezone.utc).timestamp()
        if self.source_enabled and now - self.store.get('source_update_attempt', 0) >= self.PERIOD:
            self.check_source()

    def check_source(self):
        if (not self.source_supported or self.window.paused or self.source_worker is not None
                or self.window.policy.stopped or self.window.close_when_done):
            return
        if not self.source_enabled:
            action = Action('Check and prepare a source revision', 'GitHub mihran94/JARVIS-AI main')
            self.window.gateway.run(action, self.window.confirm, self.start_source_worker)
        else:
            self.start_source_worker()

    def start_source_worker(self, candidate=None):
        if self.source_worker is not None:
            return
        ticket = self.window.policy.ticket()
        worker = SourceCheckWorker(
            installation_root(), Path(__file__).resolve().parents[1], self.store.path,
            self.window.policy, ticket, self.window.development_test_command(), self, candidate=candidate)
        if candidate is None:
            self.store.set('source_update_attempt', datetime.now(timezone.utc).timestamp())
        self.source_worker = worker
        worker.message.connect(self.finish_source_result)
        worker.prepared.connect(self.finish_source_prepared)
        worker.finished.connect(self.finish_source_worker)
        self.source_status = ('Running approved tests…' if candidate else
                              'Checking GitHub main and preparing a revision for review…')
        self.source_status_changed.emit(self.source_status)
        worker.start()
        self.window.refresh_review()

    def finish_source_prepared(self, candidate):
        """A revision is prepared. The running version is unchanged."""
        self.window.refresh_review()

    def cancel_source(self):
        if self.source_worker is not None:
            self.source_worker.requestInterruption()

    def pause(self):
        """Stop the automatic check while JARVIS is paused."""
        self.cancel_source()
        self.source_timer.stop()

    def resume(self):
        """Start the automatic check again after a pause."""
        if self.source_enabled and self.source_supported and not self.window.paused:
            self.source_timer.start(60_000)

    def finish_source_result(self, message):
        self.source_status = message
        self.store.set('source_update_status', message)
        self.source_status_changed.emit(message)
        self.window.statusBar().showMessage(message, 15000)

    def finish_source_worker(self):
        self.source_worker.deleteLater()
        self.source_worker = None
        self.window.refresh_review()
        if self.window.close_when_done:
            self.window.close()

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
    dialog.setWindowTitle('JARVIS updates & rollback')
    dialog.resize(760, 650)
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
    source_auto = QCheckBox('Automatically prepare GitHub source updates for review')
    source_auto.setChecked(checker.source_enabled)
    source_auto.setEnabled(checker.source_supported)
    source_now = QPushButton('Check and prepare a revision for review')
    source_now.setEnabled(checker.source_supported)
    source_status = QLabel(checker.source_status if checker.source_supported else
                           'Automatic source updates require the source installation launched with START_JARVIS.cmd.')
    source_status.setTextFormat(Qt.TextFormat.PlainText)
    source_status.setWordWrap(True)
    for widget in (source_auto, source_now, source_status):
        layout.addWidget(widget)
    checker.source_status_changed.connect(source_status.setText)
    prepared = QLabel('Open Review changes to authorize the test command. Once the tests pass, '
                      'you can separately approve that exact revision for the next launch.')
    prepared.setWordWrap(True)
    layout.addWidget(prepared)
    review = QPushButton('Open Review changes')
    review.clicked.connect(lambda: window.open_section('Review changes'))
    layout.addWidget(review)

    def toggle_source(enabled):
        window.notify(lambda: checker.set_source_enabled(enabled))
        blocked = source_auto.blockSignals(True)
        source_auto.setChecked(checker.source_enabled)
        source_auto.blockSignals(blocked)

    source_auto.toggled.connect(toggle_source)
    source_now.clicked.connect(lambda: window.notify(checker.check_source))
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
            if window.worker is not None or checker.source_worker is not None:
                raise ValueError('Wait for the current request or update check to finish before updating.')
            action = Action('activate_reviewed_source_update', 'Includes any listed permission/update changes', reviewed['digest'])
            def activate():
                if checker.source_worker is not None:
                    raise UpdateError('Wait for the source update check to finish.')
                backup_history(window.store.path)
                return activate_zip(root, reviewed['path'], reviewed['digest'])
            result = window.gateway.run(action, window.confirm, activate)
            report.appendPlainText('\n' + result)
            apply.setEnabled(False)
        window.notify(operation)

    def restore():
        def operation():
            if window.worker is not None or checker.source_worker is not None:
                raise ValueError('Wait for the current request or update check to finish before rollback.')
            def restore_previous():
                if checker.source_worker is not None:
                    raise UpdateError('Wait for the source update check to finish.')
                return rollback(root)
            result = window.gateway.run(Action('rollback_code', 'Select previous version; data remains unchanged'),
                                        window.confirm, restore_previous)
            report.appendPlainText('\n' + result)
        window.notify(operation)
    check.clicked.connect(lambda: checker.check())
    select.clicked.connect(choose)
    apply.clicked.connect(install)
    undo.clicked.connect(restore)
    dialog.exec()
    dialog.deleteLater()
