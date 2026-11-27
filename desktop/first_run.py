"""First-start platform and provider setup, with credentials in the OS vault."""
import sys
from keyring.errors import KeyringError
from providers.routing import set_person_provider, set_coding_provider

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QVBoxLayout,
)


def current_platform():
    return {'win32': 'Windows', 'darwin': 'macOS'}.get(sys.platform, 'Linux')


class FirstRunDialog(QDialog):
    def __init__(self, store, vault, parent=None):
        super().__init__(parent)
        self.store, self.vault = store, vault
        self.store.set('setup:started', True)
        self.setWindowTitle('Welcome to JARVIS M')
        self.resize(480, 470)
        layout = QVBoxLayout(self)
        note = QLabel('Choose this computer and your AI provider to finish setup.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.platform = QComboBox()
        self.platform.addItems(['Windows', 'macOS', 'Linux'])
        self.platform.setCurrentText(current_platform())
        form.addRow('Computer', self.platform)
        layout.addLayout(form)
        main = QGroupBox('Main Brain')
        main_form = QFormLayout(main)
        self.provider = QComboBox()
        self.provider.addItems(['Gemini', 'OpenAI', 'MiniMax', 'Ollama'])
        self.provider.setToolTip('Gemini is recommended for Tamil Live Voice and camera.')
        main_form.addRow('Provider · Gemini recommended', self.provider)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('Paste API key')
        main_form.addRow('API key', self.key)
        layout.addWidget(main)
        coding = QGroupBox('Coding Agent')
        coding_form = QFormLayout(coding)
        self.coding_provider = QComboBox()
        self.coding_provider.addItems(['OpenAI', 'MiniMax', 'Set up later'])
        coding_form.addRow('Provider', self.coding_provider)
        self.coding_key = QLineEdit()
        self.coding_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.coding_key.setPlaceholderText('Paste coding agent API key')
        coding_form.addRow('API key', self.coding_key)
        self.coding_provider.currentTextChanged.connect(self.update_coding)
        layout.addWidget(coding)
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

    def update_coding(self, provider):
        self.coding_key.clear()
        self.coding_key.setEnabled(provider != 'Set up later')

    def save(self):
        if self.platform.currentText() != current_platform():
            self.status.setText('This computer runs ' + current_platform() + '. Select it to continue.')
            return
        provider = self.provider.currentText()
        coding = self.coding_provider.currentText()
        coding_key = self.coding_key.text().strip()
        if coding != 'Set up later' and not coding_key:
            self.status.setText('Enter the Coding Agent API key, or choose Set up later.')
            return
        key = self.key.text().strip()
        if coding == provider and coding_key and key and coding_key != key:
            self.status.setText('Use the same API key when both roles use the same provider.')
            return
        if provider != 'Ollama':
            if not key:
                self.status.setText('Enter the API key for ' + provider + '.')
                return
            try:
                self.vault.put(provider, key)
            except (ValueError, RuntimeError, OSError, KeyringError):
                self.status.setText('Could not save the key in the computer credential vault.')
                return
        if coding != 'Set up later':
            try:
                self.vault.put(coding, coding_key)
            except (ValueError, RuntimeError, OSError, KeyringError):
                self.status.setText('Could not save the coding key. Retry or choose Set up later.')
                return
            set_coding_provider(self.store, coding)
        self.key.clear()
        self.coding_key.clear()
        set_person_provider(self.store, provider)
        self.store.set('setup:platform', current_platform())
        self.store.set('setup:complete', True)
        self.store.set('setup:started', False)
        self.accept()
