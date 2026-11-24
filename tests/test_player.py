"""The Quantum Visual Player: real playback, and honest reporting.

WHAT IS COVERED
    * A media file the owner chose is opened, and the controls come
      alive.
    * A file that is not there is reported as such, and the controls stay
      dead rather than pretending.
    * What the file really is — its name and its size — is shown.
    * The clock counts the time and the volume is applied.
    * A file that is not media is not offered to the player.
    * A sound file the suite made itself is opened for real.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import struct
import wave

import pytest
from PySide6.QtWidgets import QApplication

from desktop.player import MEDIA_SUFFIXES, QuantumPlayer, is_media, media_info
from desktop.prime_ui import PrimePalette

#: The media engine is optional, so the tests that need it are skipped
#: where the sound libraries are not installed.
try:
    from desktop.player import media_engine

    HAS_ENGINE = media_engine()[0] is not None
except Exception:
    HAS_ENGINE = False

needs_engine = pytest.mark.skipif(not HAS_ENGINE,
                                  reason='The media engine is not installed here.')


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def player(app):
    widget = QuantumPlayer(PrimePalette(dark=True))
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def make_wav(path, seconds=1, rate=8000):
    """A real sound file, made here so the test needs nothing."""
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b'\x00\x00' * int(rate * seconds))
    return path


def test_the_player_builds(player):
    assert player.play_button.isEnabled() is False
    assert player.status.text() == ''


@needs_engine
def test_a_file_that_is_not_there_is_reported(player, tmp_path):
    answer = player.open(tmp_path / 'nothing.wav')
    assert 'not there' in answer
    assert 'not there' in player.status.text()
    assert player.play_button.isEnabled() is False


@needs_engine
def test_a_real_media_file_is_opened(player, tmp_path):
    path = make_wav(tmp_path / 'tone.wav')
    answer = player.open(path)
    assert 'tone.wav' in answer
    assert player.play_button.isEnabled() is True
    assert player.position.isEnabled() is True
    assert 'tone.wav' in player.details.text()


@needs_engine
def test_the_details_say_how_big_the_file_is(player, tmp_path):
    path = make_wav(tmp_path / 'tone.wav')
    player.open(path)
    size = path.stat().st_size
    assert f'{size:,} bytes' in player.details.text()


@needs_engine
def test_the_volume_is_applied(player):
    player.change_volume(35)
    assert player.audio.volume() == pytest.approx(0.35, abs=0.01)
    player.change_volume(0)
    assert player.audio.volume() == 0.0


def test_the_clock_reads_as_a_time(player):
    assert player._clock(0) == '0:00'
    assert player._clock(65_000) == '1:05'
    assert player._clock(3_600_000) == '60:00'


@needs_engine
def test_playing_and_stopping_change_the_button(player, tmp_path):
    player.open(make_wav(tmp_path / 'tone.wav'))
    player.toggle()
    assert player.play_button.text() in ('Pause', 'Play')
    player.stop()
    assert player.play_button.text() == 'Play'
    assert 'Stopped' in player.status.text()


@needs_engine
def test_full_screen_is_toggled(player, tmp_path):
    player.open(make_wav(tmp_path / 'tone.wav'))
    player.toggle_fullscreen()
    assert player.video_widget.isFullScreen() is True
    assert 'full screen' in player.fullscreen_button.text().lower()
    player.toggle_fullscreen()
    assert player.video_widget.isFullScreen() is False


# ── what counts as media ───────────────────────────────────────────────────

def test_media_files_are_recognised():
    assert is_media('/tmp/clip.mp4') is True
    assert is_media('/tmp/clip.MOV') is True
    assert is_media('/tmp/song.mp3') is True
    assert is_media('/tmp/notes.txt') is False
    assert is_media('/tmp/report.pdf') is False
    assert is_media('') is False


def test_the_suffixes_are_the_usual_ones():
    for suffix in ('.mp4', '.mov', '.mkv', '.webm', '.mp3', '.wav', '.flac'):
        assert suffix in MEDIA_SUFFIXES


def test_what_a_media_file_is_can_be_asked(tmp_path):
    path = make_wav(tmp_path / 'tone.wav')
    info = media_info(path)
    assert info['exists'] is True
    assert info['name'] == 'tone.wav'
    assert info['bytes'] > 0
    missing = media_info(tmp_path / 'nothing.wav')
    assert missing['exists'] is False


def test_the_files_page_only_sends_media_to_the_player(tmp_path):
    """A file that is not media is refused with a sentence, not a crash."""
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        window.attachments = [str(tmp_path / 'notes.txt')]
        window.play_selected_in_player()
        assert 'not a video or a sound file' in window.document_status.text()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


# ── a computer without the media engine ────────────────────────────────────

def test_the_application_still_starts_without_the_media_engine(monkeypatch, tmp_path):
    """The sound libraries are not on every machine.

    An application that cannot start because it cannot play a sound is
    no good at all, so the engine is only asked for when a player is
    actually made, and its absence is reported in words.
    """
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.startswith('PySide6.QtMultimedia'):
            raise ImportError('libpulse.so.0: cannot open shared object file')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', blocked)
    import importlib

    import desktop.app as desktop

    importlib.reload(desktop)
    app = QApplication.instance() or QApplication([])
    window = desktop.Window(tmp_path)
    try:
        assert window.player_panel is not None
        assert window.player_panel.player is None
        assert 'media engine' in window.player_panel.engine_problem
        assert 'media engine' in window.player_panel.open('/tmp/anything.wav')
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
    monkeypatch.setattr(builtins, '__import__', real_import)
    importlib.reload(desktop)
