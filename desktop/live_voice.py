"""Explicit, session-only Gemini Live audio chat for the desktop."""
import base64
import binascii
import json

import numpy as np
from PySide6.QtCore import QObject, QTimer, QUrl, QUrlQuery, Signal
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QAudioSource, QMediaDevices
from PySide6.QtWebSockets import QWebSocket

from desktop.audio_test import AudioTest
from desktop.audio_echo import PlaybackEchoFilter


MODEL = 'gemini-3.8-live'
VOICE = 'Achird'
ENDPOINT = (
    'wss://generativelanguage.googleapis.com/ws/'
    'google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent'
)
OUTPUT_RATE = 24000
MAX_AUDIO_QUEUE = 2_000_000
SPEAKER_TAIL_MS = 450


def setup_message(guidance, *, tamil_tanglish=False, preferred_name=''):
    transcription = {}
    if tamil_tanglish:
        transcription = {'languageCodes': ['ta-IN', 'en-IN']}
        guidance += (
            ' The speaker regularly switches between conversational Tamil and English '
            'within one sentence. Treat the whole utterance as one turn. Preserve English '
            'words, app names and numbers in their original form. In Match My Message mode, '
            'reply naturally in spoken Tamil with English words where they fit, following '
            'the speaker’s own mix. Honor an explicit request for another reply language. '
            'If a detail is unclear, ask about only that detail instead of guessing.'
        )
    if preferred_name:
        transcription['customVocabulary'] = [preferred_name]
    setup = {
        'model': f'models/{MODEL}',
        'generationConfig': {
            'responseModalities': ['AUDIO'],
            'speechConfig': {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': VOICE}}},
        },
        'inputAudioTranscription': transcription,
        'outputAudioTranscription': {},
        'systemInstruction': {'parts': [{'text': guidance}]},
    }
    setup['realtimeInputConfig'] = {
        'activityHandling': 'START_OF_ACTIVITY_INTERRUPTS',
        'automaticActivityDetection': {'silenceDurationMs': 700, 'prefixPaddingMs': 120},
    }
    return {'setup': setup}


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
    reconnect_requested = Signal()
    state_changed = Signal(str)
    status = Signal(str)
    turn_finished = Signal(str, str)
    heard_changed = Signal(str)
    audio_level = Signal(int)
    output_level = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = 'idle'
        self.socket = None
        self.capture = self.player = None
        self.input = self.output = None
        self.pending = bytearray()
        self.echo_filter = PlaybackEchoFilter()
        self.transcript = ['', '']
        self.ignore_reply = False
        self.muted = False
        self.readout = ''
        self.readout_finished = False
        self.frame_provider = None
        self.look_request = None
        self.look_timer = QTimer(self, singleShot=True, interval=200)
        self.look_timer.timeout.connect(self.finish_look)
        self.video_timer = QTimer(self, interval=1000)
        self.video_timer.timeout.connect(self.send_camera_frame)
        self.connection_timer = QTimer(self, singleShot=True, interval=12000)
        self.connection_timer.timeout.connect(
            self.connection_timed_out)
        self.play_timer = QTimer(self, interval=20)
        self.play_timer.timeout.connect(self.flush_audio)
        self.speaker_tail = QTimer(self, singleShot=True, interval=SPEAKER_TAIL_MS)
        self.speaker_tail.timeout.connect(lambda: self.set_state('listening'))

    @property
    def active(self):
        return self.state != 'idle'

    def set_state(self, value):
        if value != self.state:
            self.state = value
            self.state_changed.emit(value)

    def set_muted(self, muted):
        if muted != self.muted:
            self.muted = muted
            if self.player is not None:
                self.player.setVolume(0.0 if muted else 1.0)

    def start(self, key, guidance, *, tamil_tanglish=False, preferred_name='', readout='',
              microphone=None, output_device=None):
        if self.active:
            return
        mic = microphone if microphone is not None else QMediaDevices.defaultAudioInput()
        speaker = output_device if output_device is not None else QMediaDevices.defaultAudioOutput()
        input_format = mic.preferredFormat()
        usable_input = (not mic.isNull() and mic.isFormatSupported(input_format)
                        and input_format.sampleFormat() in (
                            QAudioFormat.SampleFormat.Int16, QAudioFormat.SampleFormat.Float))
        self.input_format = input_format if usable_input else None
        self.output_format = None if speaker.isNull() else AudioTest.pcm_format(speaker)
        if self.output_format is None or (not readout and self.input_format is None):
            self.status.emit('Live Voice needs a working default Windows microphone and speaker.')
            return
        self.readout = readout
        self.readout_finished = False
        if not readout:
            self.capture = QAudioSource(mic, self.input_format, self)
            self.capture.stateChanged.connect(self.audio_state_changed)
        self.player = QAudioSink(speaker, self.output_format, self)
        self.player.setVolume(0.0 if self.muted else 1.0)
        self.player.stateChanged.connect(self.audio_state_changed)
        socket = self.socket = QWebSocket(parent=self)
        setup = setup_message(guidance, tamil_tanglish=tamil_tanglish, preferred_name=preferred_name)
        socket.connected.connect(lambda: self.send(setup) if self.socket is socket else None)
        socket.textMessageReceived.connect(lambda data: self.receive_from(socket, data))
        socket.binaryMessageReceived.connect(lambda data: self.receive_from(socket, bytes(data)))
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

    def look_at(self, image, question):
        socket = self.socket
        if not self.active or socket is None or self.readout or not image:
            return False
        self.look_request = (socket, image, question)
        self.look_timer.start()
        self.status.emit('Looking at the current camera view…')
        return True

    def finish_look(self):
        request, self.look_request = self.look_request, None
        if request is None:
            return
        socket, image, question = request
        if self.socket is not socket or not self.active or self.readout:
            return
        if self.frame_provider is not None:
            image = self.frame_provider()
        if not image:
            self.status.emit('Camera view is unavailable. Turn on Camera and wait for a fresh frame.')
            return
        # Bind the question to this exact frame; realtime modality streams
        # do not guarantee ordering between video and text.
        self.send({'clientContent': {'turns': [{'role': 'user', 'parts': [
            {'inlineData': {'mimeType': 'image/jpeg',
                            'data': base64.b64encode(image).decode('ascii')}},
            {'text': question},
        ]}], 'turnComplete': True}})

    def connection_lost(self, *_):
        if self.sender() is self.socket:
            reconnect = not self.readout
            self.stop('Gemini Live disconnected. Check Gemini access or start Live Voice again.')
            if reconnect:
                self.reconnect_requested.emit()

    def connection_timed_out(self):
        reconnect = not self.readout and self.state == 'connecting'
        self.stop('Gemini Live did not connect. Check your provider and network.')
        if reconnect:
            self.reconnect_requested.emit()

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
        if self.readout:
            if self.output is None:
                self.stop('Could not open the speaker for Gemini.')
                return
            self.play_timer.start()
            self.set_state('speaking')
            self.send({'realtimeInput': {'text': self.readout}})
            self.connection_timer.start(12000)
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
        self.send_camera_frame()
        self.video_timer.start()
        self.status.emit('Live Voice is listening. Speak naturally, or select Stop Live Voice to close the mic.')

    def send_audio(self):
        if self.input is None:
            return
        pcm = bytes(self.input.readAll())
        if not pcm or self.state not in ('listening', 'speaking'):
            return
        samples = microphone_pcm(pcm, self.input_format.channelCount(), self.input_format.sampleFormat())
        if not len(samples):
            return
        samples = self.echo_filter.filter(samples, self.input_format.sampleRate())
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

    def send_camera_frame(self):
        if (self.state not in ('listening', 'speaking') or self.readout
                or self.socket is None or self.frame_provider is None
                or self.socket.bytesToWrite() > 128_000):
            return
        frame = self.frame_provider()
        if frame:
            self.send({'realtimeInput': {'video': {
                'mimeType': 'image/jpeg', 'data': base64.b64encode(frame).decode('ascii'),
            }}})

    def receive_from(self, socket, raw):
        # abort/deleteLater can leave queued messages from the previous session.
        if self.socket is socket:
            self.receive(raw)

    def receive(self, raw):
        if not self.active:
            return
        socket = self.socket
        try:
            packet = json.loads(raw)
            if packet.get('error'):
                self.stop('Gemini Live could not complete the request. Check the model and connection in AI Providers.')
                return
            if 'setupComplete' in packet and self.state == 'connecting':
                self.open_audio()
                return
            if 'goAway' in packet:
                self.stop('Gemini Live ended this session. Start Live Voice to continue.')
                return
            content = packet.get('serverContent', {})
            interrupted = bool(content.get('interrupted'))
            new_speech = bool(content.get('inputTranscription', {}).get('text', '').strip())
            cutoff = interrupted or (new_speech and self.state == 'speaking')
            if cutoff:
                self.interrupt(server=True)
                if not self.active or self.socket is not socket:
                    return
            if new_speech:
                self.ignore_reply = False
            for index, field in enumerate(('inputTranscription', 'outputTranscription')):
                if index == 0 or (not self.ignore_reply and not cutoff):
                    fragment = content.get(field, {}).get('text', '')
                    self.transcript[index] = (self.transcript[index] + fragment)[:16000]
                    if index == 0 and fragment:
                        self.heard_changed.emit(self.transcript[0].strip())
                        if not self.active or self.socket is not socket:
                            return
            if not self.ignore_reply and not cutoff:
                for part in content.get('modelTurn', {}).get('parts', []):
                    data = part.get('inlineData', {})
                    if data.get('mimeType', '').startswith('audio/pcm'):
                        self.queue_audio(base64.b64decode(data['data'], validate=True))
                        if not self.active or self.socket is not socket:
                            return
            if content.get('turnComplete'):
                completed = self.transcript
                self.transcript = ['', '']
                self.ignore_reply = False
                if self.readout:
                    self.readout_finished = True
                    self.connection_timer.stop()
                    self.flush_audio()
                else:
                    self.turn_finished.emit(*(line.strip() for line in completed))
        except (AttributeError, KeyError, ValueError, TypeError, binascii.Error):
            self.stop('Gemini Live returned an unsupported audio response.')

    def queue_audio(self, raw):
        if self.output is None:
            return
        self.speaker_tail.stop()
        if self.readout:
            self.connection_timer.start(12000)
        self.pending.extend(playback_pcm(raw, self.output_format.sampleRate(),
                                         self.output_format.channelCount()))
        if len(self.pending) > MAX_AUDIO_QUEUE:
            self.stop('The speaker could not keep up with Live Voice audio.')
            return
        self.set_state('speaking')
        self.flush_audio()

    def flush_audio(self):
        if self.output is None:
            return
        if self.pending:
            available = min(len(self.pending), self.player.bytesFree())
            if available > 0:
                chunk = bytes(self.pending[:available])
                written = self.output.write(chunk)
                if written < 0:
                    self.stop('Live Voice could not write to the speaker.')
                else:
                    played = microphone_pcm(chunk[:written], self.output_format.channelCount(),
                                            self.output_format.sampleFormat())
                    if len(played):
                        if not self.muted:
                            self.echo_filter.played(played, self.output_format.sampleRate())
                        peak = max(abs(int(played.min())), abs(int(played.max())))
                        self.output_level.emit(0 if self.muted else round(peak * 100 / 32768))
                    del self.pending[:written]
        elif self.readout:
            if self.readout_finished and self.player.state() == QAudio.State.IdleState:
                self.stop('Gemini finished reading aloud.')
        elif (self.state == 'speaking' and self.player.state() == QAudio.State.IdleState
              and not self.speaker_tail.isActive()):
            self.output_level.emit(0)
            # Windows can finish playback before the speaker echo has reached the mic.
            self.speaker_tail.start()

    def interrupt(self, *, server=False):
        if self.state != 'speaking':
            return
        if self.readout:
            self.stop()
            return
        self.ignore_reply = not server
        self.speaker_tail.stop()
        self.pending.clear()
        self.output_level.emit(0)
        player = self.player
        player.reset()
        if not self.active or self.player is not player:
            return
        output = player.start()
        if not self.active or self.player is not player:
            return
        self.output = output
        if self.output is None:
            self.stop('Live Voice could not reopen the speaker.')
            return
        self.set_state('listening')


    def stop(self, message='Live Voice stopped. The microphone is closed.'):
        self.look_timer.stop()
        self.look_request = None
        if not self.active:
            return
        self.connection_timer.stop()
        self.play_timer.stop()
        self.video_timer.stop()
        self.speaker_tail.stop()
        socket, self.socket = self.socket, None
        capture, self.capture = self.capture, None
        player, self.player = self.player, None
        self.input = self.output = None
        self.pending.clear()
        self.echo_filter.clear()
        self.transcript = ['', '']
        self.ignore_reply = False
        self.readout = ''
        self.readout_finished = False
        if socket is not None:
            socket.abort()
            socket.deleteLater()
        if capture is not None:
            capture.stop()
            capture.deleteLater()
        if player is not None:
            player.reset()
            player.deleteLater()
        self.audio_level.emit(0)
        self.output_level.emit(0)
        self.set_state('idle')
        self.status.emit(message)
