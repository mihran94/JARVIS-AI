import base64
import json
import os
import struct

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QAudioFormat

from desktop.live_voice import LiveVoice, microphone_pcm, playback_pcm, setup_message


def test_live_voice_requests_audio_and_transcripts_without_action_tools():
    config = setup_message('Speak conversational Tamil or Tanglish.')['setup']
    assert config['generationConfig']['responseModalities'] == ['AUDIO']
    assert 'inputAudioTranscription' in config
    assert 'outputAudioTranscription' in config
    assert 'tools' not in config
    assert 'Tanglish' in config['systemInstruction']['parts'][0]['text']


def test_mixed_live_mode_hints_both_languages_and_allows_a_pause_between_them():
    automatic = setup_message('Friendly voice.')['setup']
    mixed = setup_message('Friendly voice.', tamil_tanglish=True)['setup']
    assert automatic['inputAudioTranscription'] == {}
    assert mixed['inputAudioTranscription']['languageCodes'] == ['ta-IN', 'en-IN']
    assert mixed['realtimeInputConfig']['automaticActivityDetection']['silenceDurationMs'] == 700
    assert 'within one sentence' in mixed['systemInstruction']['parts'][0]['text']


def test_float_windows_headset_audio_is_converted_to_signed_mono():
    raw = struct.pack('<ffffff', 0.5, 0.25, -1, -1, 1, 1)
    pcm = microphone_pcm(raw, 2, QAudioFormat.SampleFormat.Float)
    assert pcm.tolist() == [12288, -32768, 32767]


def test_completed_audio_turn_delivers_both_transcripts_once(monkeypatch):
    app = QApplication.instance() or QApplication([])
    live = LiveVoice()
    heard = []
    partial = []
    audio = []
    live.heard_changed.connect(partial.append)
    live.turn_finished.connect(lambda user, reply: heard.append((user, reply)))
    monkeypatch.setattr(live, 'queue_audio', audio.append)
    live.set_state('listening')
    raw = struct.pack('<hh', -100, 1200)
    data = base64.b64encode(raw).decode('ascii')
    live.receive(json.dumps({
        'serverContent': {
            'inputTranscription': {'text': 'என் குரல்'},
            'outputTranscription': {'text': 'கேட்குது'},
            'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm;rate=24000', 'data': data}}]},
        },
    }))
    assert audio == [raw]
    assert partial == ['என் குரல்']
    assert heard == []
    live.receive(json.dumps({'serverContent': {
        'inputTranscription': {'text': ' கேட்குதா?'},
        'outputTranscription': {'text': ', சொல்லுங்க.'},
        'turnComplete': True,
    }}))
    assert heard == [('என் குரல் கேட்குதா?', 'கேட்குது, சொல்லுங்க.')]
    assert partial == ['என் குரல்', 'என் குரல் கேட்குதா?']
    assert live.transcript == ['', '']
    assert struct.unpack('<8h', playback_pcm(raw, 48000, 2)) == (
        -100, -100, 550, 550, 1200, 1200, 1200, 1200,
    )
