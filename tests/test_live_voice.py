import base64
import json
import os
import struct
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QAudio, QAudioFormat

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


def test_name_is_a_literal_transcription_hint():
    name = 'மிஹ்ரான் பாஸ்'
    config = setup_message('Friendly voice.', tamil_tanglish=True, preferred_name=name)['setup']
    assert config['inputAudioTranscription']['customVocabulary'] == [name]


def test_camera_stream_requires_a_live_session_and_current_frame(monkeypatch):
    app = QApplication.instance() or QApplication([])
    live = LiveVoice()
    packets = []
    live.frame_provider = lambda: b'current image'
    live.socket = type('Socket', (), {'bytesToWrite': lambda _: 0})()
    monkeypatch.setattr(live, 'send', packets.append)
    live.send_camera_frame()
    assert packets == []
    live.set_state('listening')
    live.send_camera_frame()
    assert base64.b64decode(packets[-1]['realtimeInput']['video']['data']) == b'current image'
    live.frame_provider = lambda: b''
    live.send_camera_frame()
    assert len(packets) == 1


def test_camera_question_uses_latest_frame_and_cancels_when_camera_is_off(monkeypatch):
    app = QApplication.instance() or QApplication([])
    live = LiveVoice()
    packets = []
    monkeypatch.setattr(live, 'send', packets.append)
    live.socket = object()
    live.set_state('listening')
    live.frame_provider = lambda: b'latest image'
    assert live.look_at(b'old image', 'first question')
    assert live.look_at(b'old image', 'latest question')
    live.look_timer.stop()
    live.finish_look()
    content = packets[0]['clientContent']
    parts = content['turns'][0]['parts']
    assert base64.b64decode(parts[0]['inlineData']['data']) == b'latest image'
    assert parts[1]['text'] == 'latest question'
    assert content['turnComplete']
    assert live.look_at(b'old image', 'must not send')
    live.frame_provider = lambda: b''
    live.look_timer.stop()
    live.finish_look()
    assert len(packets) == 1
    assert live.look_at(b'old image', 'old session')
    live.socket = object()
    live.look_timer.stop()
    live.finish_look()
    assert len(packets) == 1


def test_microphone_waits_after_the_speaker_finishes():
    app = QApplication.instance() or QApplication([])
    live = LiveVoice()
    live.output = object()
    live.player = type('IdleSpeaker', (), {'state': lambda self: QAudio.State.IdleState})()
    live.set_state('speaking')
    live.flush_audio()
    assert live.state == 'speaking'
    assert live.speaker_tail.isActive()
    live.speaker_tail.stop()
    live.speaker_tail.timeout.emit()
    assert live.state == 'listening'


def test_provider_errors_end_the_session_without_echoing_provider_details(monkeypatch):
    app = QApplication.instance() or QApplication([])
    live = LiveVoice()
    live.set_state('listening')
    messages = []
    monkeypatch.setattr(live, 'stop', messages.append)
    live.receive(json.dumps({'error': {'message': 'private provider debug details'}}))
    assert len(messages) == 1
    assert 'AI Providers' in messages[0]
    assert 'private provider' not in messages[0]


def test_real_websocket_disconnect_requests_a_new_connection():
    # The transport acceptance needs its own event loop: prior UI tests can
    # leave timers running and starve the loopback handshake in a full suite.
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / 'scripts/check_live_reconnect.py')],
        cwd=root, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report == {'connections': 2, 'recoveries': 1,
                      'state': 'listening', 'transport': 'loopback WebSocket'}


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


def test_fragmented_playback_buffers_briefly_but_releases_short_replies(monkeypatch):
    app = QApplication.instance() or QApplication([])
    live = LiveVoice()
    fmt = QAudioFormat()
    fmt.setChannelCount(1)
    fmt.setSampleRate(24000)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    live.output_format = fmt
    writes = []
    live.output = type('Output', (), {'write': lambda _, data: writes.append(data) or len(data)})()
    live.player = type('Sink', (), {'state': lambda _: QAudio.State.IdleState,
                                     'bytesFree': lambda _: 10000})()
    now = [0.0]
    monkeypatch.setattr('desktop.live_voice.monotonic', lambda: now[0])
    packet = bytes(960)
    live.queue_audio(packet)
    assert not writes
    now[0] = 0.11
    live.flush_audio()
    assert writes == [packet]
    for _ in range(5):
        live.queue_audio(packet)
    assert writes[1:] == [5 * packet]
