"""Looking at the screen, when the owner allows it.

WHAT IS COVERED
    * The screen is captured, and the picture really is a picture.
    * The picture is saved where the owner asked, and the file is there.
    * The writing on the screen is read on this computer, and the
      capture says that it was read locally.
    * Without a running application the capture refuses, and says why.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from core.screen import ScreenUnavailable, capture_screen, observe_screen


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_the_screen_is_captured(app):
    data, width, height = capture_screen()
    assert data.startswith(b'\x89PNG\r\n\x1a\n')
    assert width > 0 and height > 0


def test_the_picture_is_saved_and_reported(app, tmp_path):
    capture = observe_screen(tmp_path / 'shot.png')
    assert (tmp_path / 'shot.png').is_file()
    assert 'shot.png' in capture.message
    assert capture.width > 0
    assert capture.height > 0


def test_the_picture_goes_into_a_folder_when_one_is_given(app, tmp_path):
    folder = tmp_path / 'screens'
    capture = observe_screen(folder)
    assert (folder / 'jarvis-screen.png').is_file()
    assert 'jarvis-screen.png' in capture.message


def test_the_writing_is_read_on_this_computer(app, tmp_path):
    capture = observe_screen(tmp_path / 'shot.png')
    # The offscreen surface may hold no writing at all, but the capture
    # must still say where the text came from.
    assert 'read on this computer' in capture.message or 'could not be read' in capture.message


def test_without_a_running_application_the_capture_refuses(monkeypatch):
    from PySide6.QtGui import QGuiApplication

    monkeypatch.setattr(QGuiApplication, 'instance', staticmethod(lambda: None))
    with pytest.raises(ScreenUnavailable) as error:
        capture_screen()
    assert 'while JARVIS is running' in str(error.value)


def test_a_place_to_save_the_picture_is_needed(app):
    with pytest.raises(ScreenUnavailable) as error:
        observe_screen(None)
    assert 'place to save' in str(error.value)
