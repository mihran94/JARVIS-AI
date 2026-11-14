"""Explicit local update UI. No requests are sent to GitHub or other services."""
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
import sqlite3
import uuid
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog, QPlainTextEdit
from core.release_status import (
    RELEASES_API_URL, RELEASES_PAGE_URL, MAX_METADATA_BYTES,
    parse_releases, ReleaseMetadataError,
)
from core.updates import (installation_root, inspect_zip, changed_files, read_state,
                          release_path, activate_zip, rollback)
from security.policy import Action


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
    report = QPlainTextEdit()
    report.setReadOnly(True)
    layout.addWidget(report)
    check = QPushButton('Check official GitHub Releases (read-only)')
    select = QPushButton('Select GitHub ZIP')
    apply = QPushButton('Approve selected update for next startup')
    apply.setEnabled(False)
    undo = QPushButton('Select previous code version (rollback)')
    for button in (check, select, apply, undo): layout.addWidget(button)
    reviewed = {}
    root = installation_root()

    network = QNetworkAccessManager(dialog)
    def check_releases():
        """Opt-in status check only: never download an archive or apply an update."""
        check.setEnabled(False)
        report.appendPlainText('\nChecking published GitHub Releases (read-only)...')
        request = QNetworkRequest(QUrl(RELEASES_API_URL))
        request.setRawHeader(b'Accept', b'application/vnd.github+json')
        request.setRawHeader(b'User-Agent', b'JARVIS-AI-release-check')
        reply = network.get(request)
        reply.downloadProgress.connect(
            lambda received, total: reply.abort() if received > MAX_METADATA_BYTES else None
        )

        def finished():
            check.setEnabled(True)
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    raise ReleaseMetadataError('GitHub check unavailable: ' + reply.errorString())
                release = parse_releases(bytes(reply.readAll()))
                if release is None:
                    message = ('No published GitHub Release yet. Source commits on main '
                               'are not a verified installable release.\n' + RELEASES_PAGE_URL)
                else:
                    label = ' (pre-release)' if release['prerelease'] else ''
                    message = ('Latest published release: ' + release['tag'] + label +
                               '\n' + release['url'] +
                               '\nReview the source and ZIP before any manual installation.')
                report.appendPlainText('\n' + message)
            except ReleaseMetadataError as error:
                report.appendPlainText('\nRelease check failed: ' + str(error))
            finally:
                reply.deleteLater()
        reply.finished.connect(finished)

    check.clicked.connect(check_releases)

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
    select.clicked.connect(choose)
    apply.clicked.connect(install)
    undo.clicked.connect(restore)
    dialog.exec()
