"""Looking at the screen, when the owner allows it.

WHAT THIS IS
    The owner can let JARVIS look at the screen. The picture is taken
    **on this computer**, it is never sent anywhere by this module, and
    the writing on it can be read **on this computer** as well.

    Two things come out of it:

    * a picture, saved where the owner can open it;
    * the writing that was on the screen, read locally, which is what
      the assistant usually wants.

WHAT THIS IS NOT
    * It does not look at the screen on its own. The caller has to ask
      for it, and the owner approves that ask through the same gateway
      as every other consequential action.
    * It does not send the picture to a provider. What is sent is the
      text that was read from it, and only when the owner lets the
      message go.
    * It does not capture a single window in particular. It captures the
      screen, and says so.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: The largest picture that is kept.
MAX_IMAGE_BYTES = 12 * 1024 * 1024

#: The name the picture is given when the owner does not choose one.
DEFAULT_NAME = 'jarvis-screen.png'


class ScreenUnavailable(RuntimeError):
    """The screen could not be captured."""


@dataclass
class ScreenCapture:
    """What was seen."""

    path: str = ''
    width: int = 0
    height: int = 0
    text: str = ''
    engine: str = ''
    message: str = ''

    def as_dict(self) -> dict:
        return {'path': self.path, 'width': self.width, 'height': self.height,
                'text': self.text, 'engine': self.engine, 'message': self.message}


def capture_screen():
    """A picture of the screen, as PNG bytes."""
    try:
        from PySide6.QtGui import QGuiApplication
    except ImportError as error:
        raise ScreenUnavailable(f'The screen could not be captured. {error}') from None
    application = QGuiApplication.instance()
    if application is None:
        raise ScreenUnavailable('The screen can only be read while JARVIS is running.')
    screen = application.primaryScreen()
    if screen is None:
        raise ScreenUnavailable('There is no screen to read.')
    picture = screen.grabWindow(0)
    if picture.isNull():
        raise ScreenUnavailable('The screen could not be captured.')
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    try:
        if not picture.save(buffer, 'PNG'):
            raise ScreenUnavailable('The screen picture could not be prepared.')
    finally:
        buffer.close()
    return bytes(data), picture.width(), picture.height()


def observe_screen(destination=None, *, language: str = 'eng', read_text: bool = True) -> ScreenCapture:
    """Take a picture of the screen, save it, and read the writing on it."""
    from core.ocr import OcrUnavailable, ocr_image_bytes

    data, width, height = capture_screen()
    if len(data) > MAX_IMAGE_BYTES:
        raise ScreenUnavailable('The screen picture is too large to keep.')

    if destination is None:
        raise ScreenUnavailable('A place to save the picture is needed.')
    target = Path(destination)
    # A place that exists as a folder, or that has no file name in it,
    # is a folder the picture goes into. A name with a suffix is the
    # name of the picture itself.
    if target.is_dir() or not target.suffix:
        target = target / DEFAULT_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    capture = ScreenCapture(path=str(target), width=width, height=height)
    if not read_text:
        capture.message = f'The screen was saved as {target.name}.'
        return capture
    try:
        capture.text = ocr_image_bytes(data, language=language)
    except OcrUnavailable as error:
        capture.message = (f'The screen was saved as {target.name}, but the writing on it '
                           f'could not be read. {error}')
        return capture
    capture.message = (f'The screen was saved as {target.name} and the writing on it was read '
                       'on this computer.')
    return capture


__all__ = ['DEFAULT_NAME', 'MAX_IMAGE_BYTES', 'ScreenCapture', 'ScreenUnavailable',
           'capture_screen', 'observe_screen']
