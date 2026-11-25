"""Explicit, session-only Gemini Live audio chat for the desktop."""
import base64
import binascii
import json

import numpy as np
from PySide6.QtCore import QObject, QTimer, QUrl, QUrlQuery, Signal
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QAudioSource, QMediaDevices
from PySide6.QtWebSockets import QWebSocket

from desktop.audio_test import AudioTest


MODEL = 'gemini-3.8-live'
ENDPOINT = (
    'wss://generativelanguage.googleapis.com/ws/'
    'google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent'
)
OUTPUT_RATE = 24000
MAX_AUDIO_QUEUE = 2_000_000


def setup_message(guidance):
    return {'setup': {
        'model': f'models/{MODEL}',
        'generationConfig': {'responseModalities': ['AUDIO']},
        'inputAudioTranscription': {},
        'outputAudioTranscription': {},
        'systemInstruction': {'parts': [{'text': guidance}]},
    }}


def playback_pcm(raw, rate_hz, channels):
    samples = np.frombuffer(raw, dtype='<i2')
    if rate_hz != OUTPUT_RATE and len(samples):
        positions = np.arange(round(len(samples) * rate_hz / OUTPUT_RATE)) * OUTPUT_RATE / rate_hz
        samples = np.interp(positions, np.arange(len(samples)), samples).astype('<i2')
    return np.repeat(samples, channels).tobytes()


def microphone_pcm(raw, channels, sample_format):
    is_float = sample_format == QAudioFormat.SampleFormat.Float
    dtype = np.dtype('<f4' if is_float else '<i2')
    frame_bytes = channels * dtype.itemsize
    usable = len(raw) - len(raw) % frame_bytes
    samples = np.frombuffer(raw[:usable], dtype=dtype)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if is_float:
        samples = np.nan_to_num(samples, nan=0.0)
        samples = np.clip(samples, -1.0, 32767 / 32768) * 32768
    return samples.astype('<i2', copy=False)


class LiveVoice(QObject):
    state_changed = Signal(str)
    status = Signal(str)
    turn_finished = Signal(str, str)
    audio_level = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = 'idle'
        self.socket = None
        self.capture = self.player = None
        self.input = self.output = None
        self.pending = bytearray()
        self.transcript = ['', '']
        self.ignore_reply = False
        self.connection_timer = QTimer(self, singleShot=True, interval=12000)
        self.connection_timer.timeout.connect(
            lambda: self.stop('Gemini Live did not connect. Check your provider and network.'))
        self.play_timer = QTimer(self, interval=20)
        self.play_timer.timeout.connect(self.flush_audio)

    @property
    def active(self):
        return self.state != 'idle'

    def set_state(self, value):
        if value != self.state:
            self.state = value
            self.state_changed.emit(value)

    def start(self, key, guidance):
        if self.active:
            return
        mic = QMediaDevices.defaultAudioInput()
        speaker = QMediaDevices.defaultAudioOutput()
        input_format = mic.preferredFormat()
        usable_input = (not mic.isNull() and mic.isFormatSupported(input_format)
                        and input_format.sampleFormat() in (
                            QAudioFormat.SampleFormat.Int16, QAudioFormat.SampleFormat.Float))
        self.input_format = input_format if usable_input else None
        self.output_format = None if speaker.isNull() else AudioTest.pcm_format(speaker)
        if self.input_format is None or self.output_format is None:
            self.status.emit('Live Voice needs a working default Windows microphone and speaker.')
            return
        self.capture = QAudioSource(mic, self.input_format, self)
        self.player = QAudioSink(speaker, self.output_format, self)
        self.capture.stateChanged.connect(self.audio_state_changed)
        self.player.stateChanged.connect(self.audio_state_changed)
        socket = self.socket = QWebSocket(parent=self)
        socket.connected.connect(lambda: self.send(setup_message(guidance)) if self.socket is socket else None)
        socket.textMessageReceived.connect(self.receive)
        socket.binaryMessageReceived.connect(lambda data: self.receive(bytes(data)))
        socket.errorOccurred.connect(self.connection_lost)
        socket.disconnected.connect(self.connection_lost)
        url = QUrl(ENDPOINT)
        query = QUrlQuery()
        query.addQueryItem('key', key)
        url.setQuery(query)
        self.set_state('connecting')
        self.connection_timer.start()
        socket.open(url)

    def send(self, payload):
        if self.socket is not None:
            self.socket.sendTextMessage(json.dumps(payload, separators=(',', ':')))

    def connection_lost(self, *_):
        if self.sender() is self.socket:
            self.stop('Gemini Live disconnected. Check Gemini access or start Live Voice again.')

    def audio_state_changed(self, state):
        if (state == QAudio.State.StoppedState and self.active
                and self.sender() in (self.capture, self.player)
                and self.sender().error() != QAudio.Error.NoError):
            self.stop('Live Voice lost the microphone or speaker. Check Windows audio settings.')

    def open_audio(self):
        self.connection_timer.stop()
        self.output = self.player.start()
        if self.player is None:
            return
        self.input = self.capture.start()
        if self.capture is None:
            return
        if self.input is None or self.output is None:
            self.stop('Could not open the Windows audio devices for Live Voice.')
            return
        self.input.readyRead.connect(self.send_audio)
        self.play_timer.start()
        self.set_state('listening')
        self.status.emit('Live Voice is listening. Speak naturally, or select Stop Live Voice to close the mic.')

    def send_audio(self):
        if self.input is None:
            return
        pcm = bytes(self.input.readAll())
        if not pcm or self.state == 'speaking':
            return
        samples = microphone_pcm(pcm, self.input_format.channelCount(), self.input_format.sampleFormat())
        if not len(samples):
            return
        peak = max(abs(int(samples.min())), abs(int(samples.max())))
        self.audio_level.emit(round(peak * 100 / 32768))
        if self.socket is not None and self.socket.bytesToWrite() > 128_000:
            self.stop('Live Voice connection is too slow to keep up with microphone audio.')
            return
        rate = self.input_format.sampleRate()
        self.send({'realtimeInput': {'audio': {
            'mimeType': f'audio/pcm;rate={rate}',
            'data': base64.b64encode(samples.tobytes()).decode('ascii'),
        }}})

    def receive(self, raw):
        if not self.active:
            return
        try:
            packet = json.loads(raw)
            if 'setupComplete' in packet and self.state == 'connecting':
                self.open_audio()
                return
            if 'goAway' in packet:
                self.stop('Gemini Live ended this session. Start Live Voice to continue.')
                return
            content = packet.get('serverContent', {})
            if content.get('interrupted'):
                self.interrupt()
            for index, field in enumerate(('inputTranscription', 'outputTranscription')):
                if index == 0 or not self.ignore_reply:
                    self.transcript[index] = (
                        self.transcript[index] + content.get(field, {}).get('text', ''))[:16000]
            if not self.ignore_reply:
                for part in content.get('modelTurn', {}).get('parts', []):
                    data = part.get('inlineData', {})
                    if data.get('mimeType', '').startswith('audio/pcm'):
                        self.queue_audio(base64.b64decode(data['data'], validate=True))
            if content.get('turnComplete'):
                self.turn_finished.emit(*(line.strip() for line in self.transcript))
                self.transcript = ['', '']
                self.ignore_reply = False
        except (AttributeError, KeyError, ValueError, TypeError, binascii.Error):
            self.stop('Gemini Live returned an unsupported audio response.')

    def queue_audio(self, raw):
        if self.output is None:
            return
        self.pending.extend(playback_pcm(raw, self.output_format.sampleRate(),
                                         self.output_format.channelCount()))
        if len(self.pending) > MAX_AUDIO_QUEUE:
            self.stop('The speaker could not keep up with Live Voice audio.')
            return
        self.audio_level.emit(0)
        self.set_state('speaking')
        self.flush_audio()

    def flush_audio(self):
        if self.output is None:
            return
        if self.pending:
            available = min(len(self.pending), self.player.bytesFree())
            if available > 0:
                written = self.output.write(bytes(self.pending[:available]))
                if written < 0:
                    self.stop('Live Voice could not write to the speaker.')
                else:
                    del self.pending[:written]
        elif self.state == 'speaking' and self.player.state() == QAudio.State.IdleState:
            self.set_state('listening')

    def interrupt(self):
        if self.state != 'speaking':
            return
        self.ignore_reply = True
        self.pending.clear()
        self.player.reset()
        self.output = self.player.start()
        if self.output is None:
            self.stop('Live Voice could not reopen the speaker.')
            return
        self.set_state('listening')

    def stop(self, message='Live Voice stopped. The microphone is closed.'):
        if not self.active:
            return
        self.connection_timer.stop()
        self.play_timer.stop()
        socket, self.socket = self.socket, None
        capture, self.capture = self.capture, None
        player, self.player = self.player, None
        self.input = self.output = None
        self.pending.clear()
        self.transcript = ['', '']
        self.ignore_reply = False
        socket.abort()
        socket.deleteLater()
        capture.stop()
        capture.deleteLater()
        player.reset()
        player.deleteLater()
        self.audio_level.emit(0)
        self.set_state('idle')
        self.status.emit(message)
