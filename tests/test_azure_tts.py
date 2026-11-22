import asyncio
import io
import os
import sys
import wave
from xml.etree import ElementTree

import httpx
import pytest

from voice import azure_tts
from voice.errors import VoiceUnavailable


@pytest.mark.parametrize(('text', 'lang'), [
    ('Hello, this is your report.', 'en'),
    ('Bonjour, voici votre rapport.', 'fr'),
    ('வணக்கம், உங்கள் அறிக்கை தயார்.', 'ta'),
    ('Vanakkam, report ready. Ippa open pannunga.', 'ta'),
])
def test_language_selection_and_tanglish(text, lang):
    actual, spoken = azure_tts.speech_text(text)
    assert actual == lang
    if 'Vanakkam' in text:
        assert spoken == 'வணக்கம், report ready. இப்போ open பண்ணுங்க.'


def test_live_catalogue_check_precedes_escaped_ssml():
    locale, name = azure_tts.VOICES['ta']
    visited = []

    def respond(request):
        assert request.url.host == 'francecentral.tts.speech.microsoft.com'
        assert request.headers['Ocp-Apim-Subscription-Key'] == 'test-only'
        visited.append((request.method, request.url.path))
        if request.method == 'GET':
            assert request.content == b''
            return httpx.Response(200, json=[{'Locale': locale, 'ShortName': name}])
        assert request.headers['X-Microsoft-OutputFormat'] == 'riff-24khz-16bit-mono-pcm'
        voice = ElementTree.fromstring(request.content)[0]
        assert voice.attrib['name'] == name
        assert voice.text == 'தமிழ் < & >'
        return httpx.Response(200, content=b'example')

    audio = asyncio.run(azure_tts.synthesize(
        azure_tts.AzureConfig('francecentral', 'test-only'), 'தமிழ் < & >', 'ta',
        transport=httpx.MockTransport(respond)))
    assert audio == b'example'
    assert visited == [('GET', '/cognitiveservices/voices/list'), ('POST', '/cognitiveservices/v1')]


@pytest.mark.parametrize(('status', 'payload', 'message'), [
    (401, {'detail': 'secret'}, 'rejected'),
    (429, {'detail': 'secret'}, 'quota'),
    (200, [], 'unavailable'),
    (302, {}, 'HTTP 302'),
])
def test_catalogue_failures_never_send_reply_text(status, payload, message):
    def respond(request):
        assert request.method == 'GET'
        return httpx.Response(status, json=payload, headers={'Location': 'https://example.com'})
    with pytest.raises(VoiceUnavailable, match=message) as error:
        asyncio.run(azure_tts.synthesize(azure_tts.AzureConfig('francecentral', 'secret'),
                                        'private text', 'en', transport=httpx.MockTransport(respond)))
    assert 'secret' not in str(error.value)


def test_cancelling_stops_inflight_synthesis(monkeypatch):
    started = False
    closed = False

    async def pending(*args):
        nonlocal started, closed
        started = True
        try:
            await asyncio.sleep(30)
        finally:
            closed = True

    monkeypatch.setattr(azure_tts, 'synthesize', pending)
    assert asyncio.run(azure_tts.cancellable_synthesis(None, '', 'en', lambda: started)) is None
    assert started and closed


def test_windows_audio_adapter_dispatches_and_stops(monkeypatch):
    from types import SimpleNamespace

    calls = []
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as audio:
        audio.setparams((1, 2, 24000, 0, 'NONE', ''))
        audio.writeframes(b'\x00\x00' * 100)
    monkeypatch.setattr(azure_tts, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setitem(sys.modules, 'winsound', SimpleNamespace(
        SND_FILENAME=1, SND_ASYNC=2, SND_NODEFAULT=4, PlaySound=lambda *args: calls.append(args)))
    azure_tts.play_wav(buffer.getvalue(), lambda: False, lambda: calls.append('playing'))
    assert calls[0][0].endswith('reply.wav')
    assert calls[1:] == ['playing', (None, 0)]


@pytest.mark.parametrize('language', ['ta', 'en', 'fr'])
@pytest.mark.skipif(sys.platform != 'win32' or os.getenv('JARVIS_AZURE_LIVE_AUDIO') != '1',
                    reason='Requires a real Windows output device and explicit live Azure opt-in')
def test_live_windows_azure_playback(language):
    from security.vault import Vault

    config = azure_tts.AzureConfig(os.environ['JARVIS_AZURE_REGION'], Vault().get(azure_tts.CREDENTIAL))
    audio = asyncio.run(azure_tts.synthesize(config, azure_tts.SAMPLES[language], language))
    playback = []
    azure_tts.play_wav(audio, lambda: False, lambda: playback.append(True))
    assert playback == [True]


def test_settings_require_owner_consent_and_store_key_in_vault(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    storage = {}

    class FakeVault:
        def put(self, provider, key):
            storage[provider] = key

        def get(self, provider):
            return storage.get(provider, '')

    try:
        window.vault = FakeVault()
        settings = window.azure_voice
        settings.region.setText('FranceCentral')
        settings.key.setText('mock-key')
        settings.save()
        assert storage == {'Azure Speech': 'mock-key'}
        assert settings.key.text() == ''
        assert b'mock-key' not in (tmp_path / 'history.sqlite3').read_bytes()
        assert settings.config() is None

        monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
        settings.allow.setChecked(True)
        assert settings.config() is None
        assert not settings.allow.isChecked()

        monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
        settings.allow.setChecked(True)
        assert settings.config().region == 'francecentral'
        assert settings.config().key == 'mock-key'
        settings.region.setText('westeurope')
        settings.save()
        assert settings.config() is None
        assert not settings.allow.isChecked()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
