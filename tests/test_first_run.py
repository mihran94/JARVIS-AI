import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QDialog
from core.store import Store
from desktop.first_run import FirstRunDialog, current_platform
from providers.routing import person_provider


class FakeVault:
    def __init__(self):
        self.saved = {}

    def put(self, provider, key):
        self.saved[provider] = key


def test_setup_requires_key_and_saves_it_only_to_vault(tmp_path):
    app = QApplication.instance() or QApplication([])
    store, vault = Store(tmp_path / 'history.sqlite3'), FakeVault()
    dialog = FirstRunDialog(store, vault)
    assert dialog.platform.currentText() == current_platform()
    dialog.save()
    assert not store.get('setup:complete')
    dialog.key.setText('test-key')
    dialog.save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert vault.saved == {'Gemini': 'test-key'}
    assert person_provider(store) == 'Gemini'
    assert not dialog.key.text()
    assert store.get('setup:complete')
    assert 'test-key' not in str(store.get('setup:platform'))


def test_local_setup_has_no_api_key_and_wrong_platform_does_not_complete(tmp_path):
    app = QApplication.instance() or QApplication([])
    store, vault = Store(tmp_path / 'history.sqlite3'), FakeVault()
    dialog = FirstRunDialog(store, vault)
    dialog.platform.setCurrentText('macOS' if current_platform() != 'macOS' else 'Windows')
    dialog.provider.setCurrentText('Ollama')
    dialog.save()
    assert not store.get('setup:complete')
    dialog.platform.setCurrentText(current_platform())
    dialog.save()
    assert store.get('setup:complete')
    assert person_provider(store) == 'Ollama'
    assert vault.saved == {}
