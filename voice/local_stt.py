"""Offline Tamil and mixed-language microphone transcription."""
from functools import lru_cache
from importlib.util import find_spec
import os
from pathlib import Path
from time import monotonic

from core.runtime_profile import DATA_FOLDER
from voice.errors import VoiceError, VoiceUnavailable
from voice.wake import WakePhraseMatcher

SAMPLE_RATE = 16000
MODEL_FILES = ('config.json', 'model.bin', 'tokenizer.json')
SETUP_HINT = 'Install the local Whisper voice dependencies and multilingual model.'


def model_path():
    override = os.environ.get('JARVIS_LOCAL_STT_MODEL')
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share')))
    return Path(override).expanduser() if override else (
        local / DATA_FOLDER / 'voice-models' / 'faster-whisper-base')


def ready():
    return (all(find_spec(name) is not None for name in ('faster_whisper', 'sounddevice'))
            and all((model_path() / file).is_file() for file in MODEL_FILES))


@lru_cache(maxsize=1)
def _load_model(path):
    from faster_whisper import WhisperModel

    model = WhisperModel(str(path), device='cpu', compute_type='int8', local_files_only=True)
    if not model.model.is_multilingual:
        raise VoiceUnavailable('Choose a multilingual Whisper model for Tamil and Tanglish.')
    return model


def transcribe(model, audio, language):
    # Both modes are Tamil-led. Auto-detecting a short mixed utterance can
    # select an unrelated language before the Tamil part is decoded.
    prompt = ('தமிழ் உரையாடலில் English வார்த்தைகளும் வரும்.'
              if language == 'ta_en' else None)
    segments, _ = model.transcribe(
        audio, language='ta', initial_prompt=prompt,
        task='transcribe', beam_size=3,
        condition_on_previous_text=False, vad_filter=True)
    return ' '.join(segment.text.strip() for segment in segments if segment.text.strip())


class LocalSpeechRecognizer:
    def __init__(self, consent, language):
        if not ready():
            raise VoiceUnavailable(SETUP_HINT)
        self._consent = consent
        self._language = language
        self._interrupted = lambda: False
        self._level = None
        self._matcher = WakePhraseMatcher()

    def set_cancel_check(self, interrupted):
        self._interrupted = interrupted

    def set_level_listener(self, listener):
        self._level = listener

    def _capture(self, seconds):
        import numpy as np
        import sounddevice as sd

        rate = SAMPLE_RATE
        try:
            sd.check_input_settings(channels=1, samplerate=rate, dtype='float32')
        except sd.PortAudioError:
            rate = round(sd.query_devices(kind='input')['default_samplerate'])
        frames = []
        heard_at = None
        block = max(1, rate // 20)
        with sd.InputStream(samplerate=rate, channels=1, dtype='float32',
                            blocksize=block) as stream:
            deadline = monotonic() + seconds
            while not self._interrupted() and monotonic() < deadline:
                self._consent.require_listening()
                samples, _ = stream.read(block)
                samples = samples[:, 0].copy()
                frames.append(samples)
                energy = float(np.sqrt(np.mean(samples ** 2)))
                if self._level is not None:
                    self._level(min(100, round(energy * 400)))
                if energy >= 0.006:
                    heard_at = monotonic()
                elif heard_at is not None and monotonic() - heard_at >= 0.8:
                    break
        if heard_at is None or self._interrupted():
            return None
        audio = np.concatenate(frames)
        if rate != SAMPLE_RATE:
            indices = np.arange(round(audio.size * SAMPLE_RATE / rate)) * rate / SAMPLE_RATE
            audio = np.interp(indices, np.arange(audio.size), audio).astype(np.float32)
        return audio

    def recognize_once(self, timeout_seconds=5.0):
        self._consent.require_listening()
        try:
            model = _load_model(model_path().resolve())
            self._consent.require_listening()
            if self._interrupted():
                return ''
            audio = self._capture(max(0.1, min(float(timeout_seconds), 30.0)))
            if audio is None:
                return ''
            self._consent.require_listening()
            result = transcribe(model, audio, self._language)
            return result if self._consent.listening and not self._interrupted() else ''
        except VoiceError:
            raise
        except (ImportError, OSError, RuntimeError, ValueError) as error:
            raise VoiceUnavailable(
                'Offline speech could not start. Check the local model and microphone.') from error

    def wait_for_wake_phrase(self, timeout_seconds=5.0):
        transcript = self.recognize_once(timeout_seconds)
        match = self._matcher.match(transcript, 'ta')
        if not match.is_wake_call:
            return '', ''
        return match.matched_phrase, self._matcher.extract_command(transcript) or ''

    def stop(self):
        # InputStream is closed as soon as the capture context exits.
        self._interrupted = lambda: True
