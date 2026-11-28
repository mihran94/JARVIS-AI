"""Full-duplex mic delivery and interruption without real devices or a key."""
import base64
import json
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
import pytest
from PySide6.QtMultimedia import QAudioFormat
from PySide6.QtWidgets import QApplication

from desktop.audio_echo import PlaybackEchoFilter
from desktop.live_voice import LiveVoice, setup_message


@pytest.mark.parametrize('noise_reduction', [False, True])
def test_microphone_stays_connected_while_gemini_is_speaking(monkeypatch, noise_reduction):
    app = QApplication.instance() or QApplication([])
    live = LiveVoice()
    live.noise_reduction = noise_reduction
    samples = (50 * np.sin(2 * np.pi * 650 * np.arange(640) / 16000)).astype('<i2')
    live.input = type('Input', (), {'readAll': lambda _: samples.tobytes()})()
    fmt = QAudioFormat()
    fmt.setSampleRate(16000)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    live.input_format = fmt
    packets = []
    monkeypatch.setattr(live, 'send', packets.append)
    live.set_state('speaking')
    live.send_audio()
    delivered = np.frombuffer(base64.b64decode(packets[0]['realtimeInput']['audio']['data']), dtype='<i2')
    assert len(delivered) == len(samples)
    if noise_reduction:
        assert np.sqrt(np.mean(delivered.astype(float) ** 2)) > .95 * np.sqrt(np.mean(samples.astype(float) ** 2))
    else:
        assert np.array_equal(delivered, samples)
    assert setup_message('Listen naturally')['setup']['realtimeInputConfig']['activityHandling'] == 'START_OF_ACTIVITY_INTERRUPTS'


def test_user_speech_clears_buffered_reply_and_next_reply_is_not_discarded(monkeypatch):
    app = QApplication.instance() or QApplication([])
    live = LiveVoice()
    events = []
    live.player = type('Speaker', (), {
        'reset': lambda _: events.append('reset'), 'start': lambda _: object(),
    })()
    live.pending.extend(b'old reply')
    live.set_state('speaking')
    live.receive(json.dumps({'serverContent': {'inputTranscription': {'text': 'ஜார்விஸ், கேளு'}}}))
    assert events == ['reset']
    assert not live.pending
    assert live.state == 'listening'
    assert not live.ignore_reply
    audio = []
    monkeypatch.setattr(live, 'queue_audio', audio.append)
    live.receive(json.dumps({'serverContent': {'modelTurn': {'parts': [
        {'inlineData': {'mimeType': 'audio/pcm;rate=24000', 'data': base64.b64encode(b'new reply').decode()}}
    ]}}}))
    assert audio == [b'new reply']


def test_playback_copy_is_suppressed_but_new_speech_passes_through():
    rng = np.random.default_rng(12)
    reference = rng.integers(-8000, 8000, 800, dtype=np.int16)
    echo = PlaybackEchoFilter()
    echo.played(reference, 2000)
    copied = (reference[400:500] * 0.5).astype(np.int16)
    assert not echo.filter(copied, 2000).any()
    user = rng.integers(-12000, 12000, 100, dtype=np.int16)
    assert np.array_equal(echo.filter(user, 2000), user)
    mixed = (copied.astype(np.int32) + user).astype(np.int16)
    assert np.array_equal(echo.filter(mixed, 2000), mixed)


def test_replacement_command_survives_late_interruption_marker():
    app = QApplication.instance() or QApplication([])
    live = LiveVoice()
    live.player = type('Speaker', (), {'reset': lambda _: None, 'start': lambda _: object()})()
    live.transcript = ['open Calculator', 'old response']
    live.set_state('speaking')
    turns = []
    live.turn_finished.connect(lambda question, reply: turns.append((question, reply)))
    for packet in (
        {'inputTranscription': {'text': 'Notepad'}},
        {'interrupted': True, 'turnComplete': True, 'outputTranscription': {'text': 'old audio'}},
        {'inputTranscription': {'text': ' திற'}, 'outputTranscription': {'text': 'சரி'}},
        {'turnComplete': True},
    ):
        live.receive(json.dumps({'serverContent': packet}))
    assert turns == [('Notepad திற', 'சரி')]


def test_stopped_reply_cannot_dispatch_the_abandoned_command():
    app = QApplication.instance() or QApplication([])
    live = LiveVoice()
    live.player = type('Speaker', (), {'reset': lambda _: None, 'start': lambda _: object()})()
    live.transcript = ['open Calculator', 'old response']
    live.set_state('speaking')
    turns = []
    live.turn_finished.connect(lambda *turn: turns.append(turn))
    live.interrupt()
    live.receive('{"serverContent":{"outputTranscription":{"text":"late text"},"turnComplete":true}}')
    assert turns == []
