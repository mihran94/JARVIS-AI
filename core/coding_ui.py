"""Qt-thread UI with background read-only filesystem operations."""
from pathlib import Path
from threading import Thread
from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                            QLabel, QListWidget, QListWidgetItem, QTextEdit,
                            QFileDialog, QSplitter)
from core.coding_workspace import ProjectWorkspace, diagnose_traceback


class _Results(QObject):
    ready = pyqtSignal(object, object)


class CodingPanel(QWidget):
    def __init__(self, palette, parent=None, open_providers=None):
        super().__init__(parent)
        self.workspace = None
        self.relative = Path('.')
        self._busy = False
        self._results = _Results(self)
        self._results.ready.connect(self._finish)
        self.setFont(QFont('Courier New', 9))
        self.setStyleSheet(f'QWidget {{ color: {palette.TEXT}; background: {palette.PANEL}; }} '
                          f'QPushButton {{ border: 1px solid {palette.BORDER}; padding: 6px; }} '
                          f'QPushButton:focus {{ border: 1px solid {palette.PRI}; }}')
        layout = QVBoxLayout(self)
        title = QLabel('CODING · Project Explorer + Error Doctor')
        title.setWordWrap(True)
        layout.addWidget(title)
        note = QLabel('Local, read-only tools. Choose a project folder; double-click a folder or file.\nCommon credential files are hidden; other files may still contain secrets.')
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.choose = QPushButton('Choose project')
        self.choose.clicked.connect(self._choose)
        row.addWidget(self.choose)
        self.up = QPushButton('Parent folder')
        self.up.setEnabled(False)
        self.up.clicked.connect(self._up)
        row.addWidget(self.up)
        layout.addLayout(row)
        connections = QHBoxLayout()
        self.providers_button = QPushButton('AI connections: Gemini / OpenAI / MiniMax')
        self.providers_button.setEnabled(open_providers is not None)
        if open_providers is not None:
            self.providers_button.clicked.connect(open_providers)
        connections.addWidget(self.providers_button)
        self.codex_button = QPushButton('Codex review…')
        self.codex_button.clicked.connect(self._codex)
        connections.addWidget(self.codex_button)
        updater = QPushButton("Update project ZIP…")
        updater.clicked.connect(self._update_zip)
        connections.addWidget(updater)
        layout.addLayout(connections)
        self.status = QLabel('No project selected')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.files = QListWidget()
        self.files.setAccessibleName('Project files')
        self.files.itemDoubleClicked.connect(self._open)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName('Source preview')
        split.addWidget(self.files)
        split.addWidget(self.preview)
        layout.addWidget(split, 2)
        self.error_input = QTextEdit()
        self.error_input.setPlaceholderText('Paste a Python traceback here (remove secrets first)')
        self.error_input.setAcceptRichText(False)
        self.error_input.setAccessibleName('Python traceback')
        layout.addWidget(self.error_input, 1)
        analyze = QPushButton('Explain error locally')
        analyze.clicked.connect(self._diagnose)
        layout.addWidget(analyze)
        self.diagnosis = QTextEdit()
        self.diagnosis.setReadOnly(True)
        self.diagnosis.setAccessibleName('Error guidance')
        layout.addWidget(self.diagnosis, 1)

    def _update_zip(self):
        from core.project_update_ui import ProjectUpdateDialog
        ProjectUpdateDialog(self).exec()

    def _codex(self):
        if self.workspace is None:
            self.status.setText('Choose a project folder before opening Codex.')
            return
        from core.codex_ui import CodexReviewDialog
        dialog = CodexReviewDialog(self.workspace.root, self)
        dialog.exec()

    def _diagnose(self):
        self.diagnosis.setPlainText(diagnose_traceback(self.error_input.toPlainText()))

    def _choose(self):
        path = QFileDialog.getExistingDirectory(self, 'Choose project folder')
        if path:
            self.select_project(path)

    def select_project(self, path):
        def select():
            workspace = ProjectWorkspace(path)
            return ('folder', workspace, Path('.'), workspace.list_directory())
        self._start(select)

    def _start(self, work):
        if self._busy:
            return
        self._busy = True
        self.choose.setEnabled(False)
        self.up.setEnabled(False)
        self.files.setEnabled(False)
        self.status.setText('Reading project…')
        def run():
            try:
                result, error = work(), None
            except Exception as exc:
                result, error = None, str(exc)
            try:
                self._results.ready.emit(result, error)
            except RuntimeError:
                pass  # Window was destroyed while the read completed.
        Thread(target=run, daemon=True).start()

    def _folder(self, relative):
        workspace = self.workspace
        self._start(lambda: ('folder', workspace, relative, workspace.list_directory(relative)))

    def _up(self):
        if self.workspace and self.relative != Path('.'):
            self._folder(self.relative.parent)

    def _open(self, item):
        if not self.workspace:
            return
        name, directory = item.data(Qt.ItemDataRole.UserRole)
        relative = self.relative / name
        if directory:
            self._folder(relative)
        else:
            workspace = self.workspace
            self._start(lambda: ('file', relative, workspace.read_text(relative)))

    def _finish(self, result, error):
        self._busy = False
        self.choose.setEnabled(True)
        self.files.setEnabled(True)
        if error:
            self.status.setText(f'Could not read: {error}')
            self.preview.clear()
        elif result[0] == 'folder':
            _, self.workspace, self.relative, (entries, truncated) = result
            self.files.clear()
            self.preview.clear()
            for name, directory in entries:
                item = QListWidgetItem(('Folder: ' if directory else '') + name)
                item.setData(Qt.ItemDataRole.UserRole, (name, directory))
                self.files.addItem(item)
            suffix = ' · Showing first 500 entries' if truncated else ''
            self.status.setText(f'{self.workspace.root} / {self.relative}{suffix}')
        else:
            self.preview.setPlainText(result[2])
            self.status.setText(str(self.workspace.root / result[1]))
        self.up.setEnabled(self.workspace is not None and self.relative != Path('.'))
