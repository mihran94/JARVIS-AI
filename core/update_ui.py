"""Updates dialog. Workers emit signals; widgets stay on the Qt thread."""
import threading
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTextEdit, QVBoxLayout)
from PyQt6.QtGui import QFont
from core import updater
from memory.config_manager import get_update_settings, save_update_settings


class UpdateDialog(QDialog):
    completed = pyqtSignal(object, str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = root
        self.manifest = None
        self.setWindowTitle('Jarvis-Blue — Updates')
        self.resize(580, 470)
        self.setFont(QFont('Courier New', 9))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'Current version: {updater.installed(root)} · Source edition'))
        self.mode = QComboBox()
        self.mode.addItems(['Notify Only', 'Off'])
        settings = get_update_settings()
        self.mode.setCurrentIndex(1 if settings['mode'] == 'off' else 0)
        layout.addWidget(self.mode)
        layout.addWidget(QLabel('Release feed URL (HTTPS)'))
        self.url = QLineEdit(settings['manifest_url'])
        self.url.setPlaceholderText('Not connected — configure your project release feed')
        layout.addWidget(self.url)
        self.status = QLabel('Updates are installed only when you choose Install & Restart.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        layout.addWidget(self.notes)
        self.buttons = []
        row = QHBoxLayout()
        for label, callback in [('Save', self.save), ('Check for Updates', self.check),
                                ('Download', self.download), ('Install & Restart', self.apply)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.buttons.append(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        for label, callback in [('Update History', self.show_history),
                                ('Restore Previous Version', self.rollback)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.buttons.append(button)
        layout.addLayout(row)
        self.completed.connect(self.finish)
        self.refresh()

    def refresh(self):
        self.buttons[2].setEnabled(bool(self.manifest and self.manifest['available']))
        self.buttons[3].setEnabled((self.root / '.updates/pending.json').exists())
        self.buttons[5].setEnabled((self.root / '.updates/backup.json').exists())

    def save(self):
        try:
            save_update_settings(self.url.text(), 'off' if self.mode.currentIndex() else 'notify')
            self.status.setText('Update preferences saved.')
        except Exception as error:
            self.status.setText(str(error))

    def work(self, function):
        for button in self.buttons:
            button.setEnabled(False)
        self._busy = True
        self.status.setText('Working…')
        def run():
            try:
                self.completed.emit(function(), '')
            except Exception as error:
                self.completed.emit(None, str(error))
        threading.Thread(target=run, daemon=True).start()

    def reject(self):
        if not getattr(self, '_busy', False):
            super().reject()

    def finish(self, result, error):
        self._busy = False
        for button in self.buttons:
            button.setEnabled(True)
        if error:
            self.status.setText('Update failed: ' + error)
        elif isinstance(result, dict):
            self.manifest = result
            self.status.setText('New version: ' + result['version'] if result['available'] else 'You are up to date.')
            self.notes.setPlainText(result['notes'])
        else:
            self.status.setText(str(result))
        self.refresh()

    def check(self):
        url = self.url.text().strip()
        self.manifest = None
        self.work(lambda: updater.check(url, updater.installed(self.root)))

    def download(self):
        manifest = dict(self.manifest)
        self.work(lambda: updater.stage(self.root, manifest))

    def show_history(self):
        try:
            rows = updater.history(self.root)
            self.notes.setPlainText('\n'.join(f"{r['time']}  {r['action']}  {r['version']}" for r in rows) or 'No updates installed yet.')
        except Exception as error:
            self.status.setText(str(error))

    def apply(self, rollback=False):
        # clicked(bool) must not accidentally select rollback.
        rollback = False
        self.restart(rollback)

    def rollback(self):
        self.restart(True)

    def restart(self, rollback):
        answer = QMessageBox.question(self, 'Restart Jarvis-Blue',
            'Stop current tasks, close Jarvis-Blue and ' + ('restore the previous version?' if rollback else 'install the downloaded update?'))
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            updater.launch_helper(self.root, rollback)
            QApplication.instance().quit()
        except Exception as error:
            self.status.setText(str(error))
