import numpy as np
from desktop.audio_noise import MicrophoneRumbleFilter


def tone(frequency, amplitude=4000, rate=16000):
    return (amplitude * np.sin(2 * np.pi * frequency * np.arange(rate) / rate)).astype('<i2')


def rms(samples):
    return np.sqrt(np.mean(samples.astype(float) ** 2))


def test_rumble_and_dc_are_reduced_without_gating_quiet_speech():
    rumble = tone(20)
    cleaned = MicrophoneRumbleFilter().process(rumble, 16000)
    assert rms(cleaned[1600:]) < rms(rumble[1600:]) * .12
    quiet = tone(350, amplitude=35)
    cleaned = MicrophoneRumbleFilter().process(quiet, 16000)
    assert rms(cleaned[1600:]) > rms(quiet[1600:]) * .98
    dc = MicrophoneRumbleFilter().process(np.full(16000, 5000, dtype='<i2'), 16000)
    assert np.max(np.abs(dc[8000:])) <= 1


def test_chunk_boundaries_do_not_clip_word_onsets_or_change_length():
    signal = tone(700)
    whole = MicrophoneRumbleFilter().process(signal, 16000)
    stream = MicrophoneRumbleFilter()
    chunks = np.concatenate([stream.process(chunk, 16000) for chunk in np.array_split(signal, 50)])
    assert np.array_equal(chunks, whole)
    assert len(chunks) == len(signal) and chunks.dtype == signal.dtype
