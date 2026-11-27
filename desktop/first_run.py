"""First-start platform and provider setup, with credentials in the OS vault."""
import sys
from keyring.errors import KeyringError
from providers.routing import set_person_provider

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout,
)


def current_platform():
    return {'win32': 'Windows', 'darwin': 'macOS'}.get(sys.platform, 'Linux')


class FirstRunDialog(QDialog):
    def __init__(self, store, vault, parent=None):
        super().__init__(parent)
        self.store, self.vault = store, vault
        self.setWindowTitle('Welcome to JARVIS M')
        self.resize(440, 300)
        layout = QVBoxLayout(self)
        note = QLabel('Choose this computer and your AI provider to finish setup.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.platform = QComboBox()
        self.platform.addItems(['Windows', 'macOS', 'Linux'])
        self.platform.setCurrentText(current_platform())
        form.addRow('Computer', self.platform)
        self.provider = QComboBox()
        self.provider.addItems(['Gemini', 'OpenAI', 'MiniMax', 'Ollama'])
        form.addRow('AI provider', self.provider)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('Paste API key')
        form.addRow('API key', self.key)
        layout.addLayout(form)
        self.status = QLabel('Gemini provides Live Voice and camera understanding.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                       | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.provider.currentTextChanged.connect(self.update_provider)

    def update_provider(self, provider):
        self.key.clear()
        self.key.setEnabled(provider != 'Ollama')
        self.status.setText('Ollama needs a local server and model. No API key is required.'
                            if provider == 'Ollama' else 'Your API key is saved in this computer’s credential vault.')

    def save(self):
        if self.platform.currentText() != current_platform():
            self.status.setText('This computer runs ' + current_platform() + '. Select it to continue.')
            return
        provider = self.provider.currentText()
        if provider != 'Ollama':
            key = self.key.text().strip()
            if not key:
                self.status.setText('Enter the API key for ' + provider + '.')
                return
            try:
                self.vault.put(provider, key)
            except (ValueError, RuntimeError, OSError, KeyringError):
                self.status.setText('Could not save the key in the computer credential vault.')
                return
        self.key.clear()
        set_person_provider(self.store, provider)
        self.store.set('setup:platform', current_platform())
        self.store.set('setup:complete', True)
        self.accept()
