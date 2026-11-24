"""The Quantum Visual Player — real playback of a media file on this computer.

WHAT THIS IS
    A player that really plays. It opens a file the owner chose, plays
    it, seeks in it, changes the volume, goes full screen, and shows what
    the file really is — its duration, its size, and the shape of the
    picture.

    It is the place a downloaded file or a rendered export ends up: the
    Download Center writes a file, the video studio renders one, and
    both can be opened here to be looked at.

WHAT THIS IS NOT
    * It does not download anything and it does not open a network
      stream. It plays a file that is already on this computer.
    * It does not pretend a file played. If the engine is missing, the
      codec is unknown or the file is gone, it says so in words.
    * It does not change the file. It reads it.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

#: The files the player offers to open.
MEDIA_SUFFIXES = ('.mp4', '.mov', '.m4v', '.mkv', '.webm', '.avi', '.mp3', '.wav',
                   '.m4a', '.flac', '.ogg')

#: The file dialog filter.
MEDIA_FILTER = ('Media files (*.mp4 *.mov *.m4v *.mkv *.webm *.avi *.mp3 *.wav *.m4a '
                 '*.flac *.ogg);;All files (*)')


def media_engine():
    """The media engine classes, or a sentence saying why there are none.

    The engine is not imported until a player is actually made, because
    the sound libraries it needs are not on every machine, and an
    application that cannot start because it cannot play a sound is no
    good at all.
    """
    try:
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget
    except ImportError as error:
        return None, (f'The media engine is not available on this computer, so the '
                      f'player cannot open a file. {error}')
    return (QMediaPlayer, QAudioOutput, QVideoWidget), ''


def is_media(path) -> bool:
    """Whether a path looks like a file the player can open."""
    try:
        return Path(path).suffix.casefold() in MEDIA_SUFFIXES
    except (TypeError, ValueError):
        return False


def media_info(path) -> dict:
    """What a media file really is, before anything plays it."""
    source = Path(path)
    info = {'path': str(source), 'name': source.name, 'bytes': 0, 'suffix': source.suffix,
            'exists': source.is_file()}
    if not info['exists']:
        return info
    try:
        info['bytes'] = source.stat().st_size
    except OSError:
        pass
    return info


class QuantumPlayer(QWidget):
    """Play a media file, and say what is really happening."""

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.path = None
        self._fullscreen = False
        self.engine, self.engine_problem = media_engine()

        if self.engine is not None:
            player_class, audio_class, video_class = self.engine
            self.player_class = player_class
            self.video_widget = video_class(self)
            self.player = player_class(self)
            self.audio = audio_class(self)
            self.audio.setVolume(0.7)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(self.video_widget)
            self.player.errorOccurred.connect(self.on_error)
            self.player.hasVideoChanged.connect(self.on_has_video)
            self.player.mediaStatusChanged.connect(self.on_status)
            self.player.durationChanged.connect(self.on_duration)
            self.player.positionChanged.connect(self.on_position)
        else:
            self.player_class = None
            self.video_widget = None
            self.player = None
            self.audio = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel('Quantum Visual Player')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        note = QLabel('Play a file that is already on this computer. Nothing is downloaded and '
                      'nothing is sent anywhere.')
        note.setObjectName('pageSubtitle')
        note.setWordWrap(True)
        layout.addWidget(note)

        if self.video_widget is not None:
            self.video_widget.setMinimumSize(480, 270)
            self.video_widget.setAccessibleName('The picture')
            self.video_widget.setStyleSheet(
                'background: #05070c; border: 1px solid rgba(255,255,255,26); '
                'border-radius: 14px;')
            layout.addWidget(self.video_widget, 1)
        else:
            self.picture_note = QLabel(self.engine_problem)
            self.picture_note.setWordWrap(True)
            self.picture_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.picture_note.setStyleSheet('color: #ffcf6b; font-size: 13px;')
            layout.addWidget(self.picture_note, 1)

        controls = QHBoxLayout()
        self.open_button = QPushButton('Open a file')
        self.open_button.clicked.connect(self.choose_file)
        controls.addWidget(self.open_button)
        self.play_button = QPushButton('Play')
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.toggle)
        controls.addWidget(self.play_button)
        self.stop_button = QPushButton('Stop')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        controls.addWidget(self.stop_button)
        controls.addStretch(1)
        self.fullscreen_button = QPushButton('Full screen')
        self.fullscreen_button.setEnabled(False)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        controls.addWidget(self.fullscreen_button)
        layout.addLayout(controls)

        seek_row = QHBoxLayout()
        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.setEnabled(False)
        self.position.setAccessibleName('The position in the file')
        self.position.sliderReleased.connect(self.seek_to)
        seek_row.addWidget(self.position, 1)
        self.clock = QLabel('0:00')
        self.clock.setAccessibleName('The time')
        seek_row.addWidget(self.clock)
        layout.addLayout(seek_row)

        volume_row = QHBoxLayout()
        volume_row.addWidget(QLabel('Volume'))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setFixedWidth(160)
        self.volume.setAccessibleName('The volume')
        self.volume.valueChanged.connect(self.change_volume)
        volume_row.addWidget(self.volume)
        volume_row.addStretch(1)
        layout.addLayout(volume_row)

        self.picture_note = QLabel('')
        self.picture_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture_note.setStyleSheet('color: #93a1b8; font-size: 13px;')
        self.picture_note.setVisible(False)
        layout.addWidget(self.picture_note)

        self.details = QLabel('No file is open.')
        self.details.setWordWrap(True)
        self.details.setAccessibleName('What the file is')
        layout.addWidget(self.details)

        self.status = QLabel('')
        self.status.setWordWrap(True)
        self.status.setAccessibleName('The player status')
        layout.addWidget(self.status)

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # opening

    def choose_file(self):
        """Ask the owner for a file, and open it."""
        path, _ = QFileDialog.getOpenFileName(self, 'Open a media file', '',
                                              MEDIA_FILTER)
        if path:
            self.open(path)

    def open(self, path) -> str:
        """Open a media file, and say what happened."""
        if self.player is None:
            self.status.setText(self.engine_problem)
            return self.engine_problem
        source = Path(path)
        info = media_info(source)
        if not info['exists']:
            self.status.setText(f'That file is not there any more: {source.name}')
            self.play_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.fullscreen_button.setEnabled(False)
            return 'The file is not there.'
        self.path = str(source)
        self.picture_note.setText('This file has no picture in it — it is a sound file.')
        self.picture_note.setVisible(False)
        self.player.setSource(QUrl.fromLocalFile(str(source.resolve())))
        self.player.setPosition(0)
        self.position.setEnabled(True)
        self.play_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.fullscreen_button.setEnabled(True)
        self.play_button.setText('Play')
        shape = ''
        size = f'{info["bytes"]:,} bytes'
        self.details.setText(f'{info["name"]} · {size}{shape}')
        self.status.setText('Ready. Press Play.')
        return f'{info["name"]} was opened.'

    # ------------------------------------------------------------------
    # playing

    def toggle(self):
        """Play or pause."""
        if self.player is None:
            return self.engine_problem
        if self.player.playbackState() == self.player_class.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setText('Play')
            self.status.setText('Paused.')
            return 'Paused.'
        self.player.play()
        self.play_button.setText('Pause')
        self.status.setText('Playing.')
        return 'Playing.'

    def stop(self):
        """Stop, and go back to the beginning."""
        if self.player is None:
            return self.engine_problem
        self.player.stop()
        self.player.setPosition(0)
        self.play_button.setText('Play')
        self.status.setText('Stopped.')
        return 'Stopped.'

    def seek_to(self):
        """Move to where the owner dragged the position."""
        self.player.setPosition(self.position.value())

    def change_volume(self, value):
        """Set the volume."""
        if self.audio is None:
            return
        self.audio.setVolume(max(0.0, min(1.0, value / 100)))

    def toggle_fullscreen(self):
        """Go full screen, or come back."""
        if self.video_widget is None:
            return self.engine_problem
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            self.video_widget.setFullScreen(True)
            self.fullscreen_button.setText('Leave full screen')
        else:
            self.video_widget.setFullScreen(False)
            self.fullscreen_button.setText('Full screen')
        return 'Full screen.' if self._fullscreen else 'Back to the window.'

    # ------------------------------------------------------------------
    # what the engine says

    def on_has_video(self, has_video):
        """A sound file has no picture, and the area says so."""
        self.picture_note.setVisible(not has_video and self.path is not None)

    def on_error(self, error, message=''):
        """The engine could not play the file. Say what it said."""
        detail = (message or 'The media engine could not play this file.').strip()
        self.status.setText(detail)
        self.play_button.setText('Play')

    def on_status(self, status):
        """The state of the file."""
        if self.player_class is None:
            return
        if status == self.player_class.MediaStatus.EndOfMedia:
            self.play_button.setText('Play')
            self.status.setText('The file has finished.')
        elif status == self.player_class.MediaStatus.InvalidMedia:
            self.status.setText('This file could not be read as media.')

    def on_duration(self, milliseconds):
        """The length of the file."""
        self.position.setRange(0, max(0, int(milliseconds)))
        self.clock.setText(self._clock(milliseconds))

    def on_position(self, milliseconds):
        """Where the playhead is."""
        if not self.position.isSliderDown():
            self.position.setValue(int(milliseconds))
        self.clock.setText(self._clock(milliseconds))

    @staticmethod
    def _clock(milliseconds) -> str:
        seconds = max(0, int(milliseconds or 0) // 1000)
        return f'{seconds // 60}:{seconds % 60:02d}'

    # ------------------------------------------------------------------

    def closeEvent(self, event):
        """Stop the playback before the window goes."""
        if self.player is not None:
            self.player.stop()
        super().closeEvent(event)


__all__ = ['MEDIA_FILTER', 'MEDIA_SUFFIXES', 'QuantumPlayer', 'is_media',
           'media_engine', 'media_info']
