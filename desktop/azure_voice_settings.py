"""Azure Speech preferences in the existing API Provider Manager."""
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QGroupBox, QLabel, QLineEdit,
                               QMessageBox, QPushButton)

from voice.azure_tts import AzureConfig, CREDENTIAL, SAMPLES, normalize_region
from voice.errors import VoiceUnavailable


class AzureVoiceSettings(QGroupBox):
    def __init__(self, window):
        super().__init__('Azure Speech · Neural voice')
        self.window = window
        self.characters = 0
        form = QFormLayout(self)
        self.region = QLineEdit(window.store.get('voice:azure_region', '') or '')
        self.region.setPlaceholderText('francecentral')
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('Leave blank to keep the saved key')
        form.addRow('Azure region', self.region)
        form.addRow('Azure Speech key', self.key)
        save = QPushButton('Save Azure Speech settings')
        save.clicked.connect(self.save)
        form.addRow(save)
        self.allow = QCheckBox('Allow JARVIS to send spoken text to Microsoft Azure')
        self.allow.setChecked(bool(self.region.text() and
                                  window.store.get('voice:azure_consent') == self.region.text()))
        self.allow.toggled.connect(self.set_consent)
        form.addRow(self.allow)
        notice = QLabel('Cloud voice uses the text selected for playback, including replies when '
                        'Read replies aloud is on. The microphone stays on the existing local path. '
                        'Azure may charge for synthesis.')
        notice.setWordWrap(True)
        form.addRow(notice)
        for code, language in (('ta', 'Tamil'), ('en', 'English'), ('fr', 'French')):
            button = QPushButton(f'Test {language} Voice')
            button.clicked.connect(lambda _checked=False, code=code: self.test_voice(code))
            form.addRow(button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.usage = QLabel('Estimated session usage: 0 synthesized characters')
        self.usage.setWordWrap(True)
        form.addRow(self.status)
        form.addRow(self.usage)
        window.voice_panel.cloud_config = self.config
        window.voice_panel.cloud_usage.connect(self.record_usage)
        window.voice_panel.feedback.connect(self.status.setText)

    def save(self):
        try:
            region = normalize_region(self.region.text())
            if self.key.text():
                self.window.vault.put(CREDENTIAL, self.key.text())
        except ValueError as error:
            self.status.setText(str(error))
            return
        except Exception:
            self.status.setText('Windows Credential Manager could not save the Azure key.')
            return
        changed = self.key.text() or region != self.window.store.get('voice:azure_region')
        self.key.clear()
        if changed:
            self.set_consent(False)
        self.window.store.set('voice:azure_region', region)
        self.region.setText(region)
        self.status.setText('Azure Speech settings saved. Use a language test to verify the key and audio.')

    def set_consent(self, allowed):
        window = self.window
        region = window.store.get('voice:azure_region')
        if allowed and region:
            allowed = QMessageBox.question(
                self, 'Allow Azure Speech?',
                f'Allow JARVIS to send text selected for speech playback to Microsoft Azure ({region})? '
                'This includes automatically read replies when enabled. Azure may charge for synthesis. '
                'You can revoke permission here at any time.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
        if allowed and not region:
            self.status.setText('Save your Azure Speech key and region before enabling cloud voice.')
            allowed = False
        self.allow.blockSignals(True)
        self.allow.setChecked(bool(allowed))
        self.allow.blockSignals(False)
        window.store.set('voice:azure_consent', region if allowed else None)
        if not allowed:
            window.voice_panel.cancel_cloud_speech()

    def config(self):
        window = self.window
        region = window.store.get('voice:azure_region')
        if window.policy.stopped or not region or window.store.get('voice:azure_consent') != region:
            return None
        try:
            key = window.vault.get(CREDENTIAL)
        except Exception:
            raise VoiceUnavailable('Windows Credential Manager could not read the Azure key.') from None
        if not key:
            raise VoiceUnavailable('Add an Azure Speech key in API Provider Manager.')
        return AzureConfig(region, key)

    def test_voice(self, language):
        self.window.voice_panel.speak_response(SAMPLES[language], sample_language=language)

    def record_usage(self, characters, voice):
        self.characters += characters
        self.status.setText(f'Azure synthesized audio with {voice}.')
        self.usage.setText(f'Estimated session usage: {self.characters:,} synthesized characters. '
                           'Check Azure for billing totals.')
