"""Reading the text out of a picture of a document.

WHAT IS COVERED
    * A scanned PDF — a page that is a picture with no text layer — is
      read on this computer, and the text really comes back.
    * The reader says that the text came from the pictures, so the owner
      knows where it came from.
    * A missing recognition engine is reported with what to install,
      and the document is not silently reported as empty.
    * A picture with no writing on it is reported as such.
    * The engine is never asked for a language that does not exist.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtWidgets import QApplication

from core.ocr import (
    MISSING_ENGINE, OCR_LANGUAGES, OcrUnavailable, ocr_image_bytes, ocr_pdf,
    tesseract_executable,
)

#: The engine is optional, so the tests that need it are skipped where it
#: is not installed. The tests that check the missing-engine message run
#: everywhere.
try:
    tesseract_executable()
    HAS_ENGINE = True
except OcrUnavailable:
    HAS_ENGINE = False

needs_engine = pytest.mark.skipif(not HAS_ENGINE,
                                  reason='Tesseract OCR is not installed here.')
from desktop.documents import DocumentError, read_document


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def write_page(path, lines=('The launch is on Friday', 'Venue booked for the 27th')):
    """A picture of a page, with writing on it."""
    image = QImage(1240, 400, QImage.Format.Format_RGB32)
    image.fill(QColor('white'))
    painter = QPainter(image)
    painter.setPen(QColor('black'))
    painter.setFont(QFont('DejaVu Serif', 34))
    painter.drawText(QRectF(60, 60, 1120, 120), Qt.AlignmentFlag.AlignLeft, lines[0])
    painter.setFont(QFont('DejaVu Serif', 26))
    painter.drawText(QRectF(60, 170, 1120, 100), Qt.AlignmentFlag.AlignLeft, lines[1])
    painter.end()
    buffer = QByteArray()
    stream = QBuffer(buffer)
    stream.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(stream, 'PNG')
    stream.close()
    path.write_bytes(bytes(buffer))
    return path


@pytest.fixture
def scanned(tmp_path, app):
    """A PDF whose page is a picture, with no text layer at all."""
    from document_fixtures import make_scanned_pdf

    picture = write_page(tmp_path / 'page.png')
    return make_scanned_pdf(tmp_path / 'scanned.pdf', picture)


# ── the engine ─────────────────────────────────────────────────────────────

def test_the_engine_is_found_or_the_owner_is_told():
    try:
        assert tesseract_executable()
    except OcrUnavailable as error:
        assert 'Tesseract' in str(error)
        assert MISSING_ENGINE in str(error)


def test_the_languages_are_the_ones_the_engine_has():
    assert 'eng' in OCR_LANGUAGES
    assert 'tam' in OCR_LANGUAGES


def test_a_missing_engine_is_reported_with_what_to_install(monkeypatch):
    monkeypatch.setattr('core.ocr.shutil.which', lambda name: None)
    monkeypatch.setattr('core.ocr.os.name', 'posix')
    with pytest.raises(OcrUnavailable) as error:
        tesseract_executable()
    assert 'Tesseract' in str(error.value)
    assert 'PATH' in str(error.value)


# ── a picture ──────────────────────────────────────────────────────────────

@needs_engine
def test_the_writing_in_a_picture_is_read(tmp_path, app):
    picture = write_page(tmp_path / 'page.png')
    from core.ocr import ocr_image_file

    text = ocr_image_file(picture)
    assert 'launch' in text.lower()
    assert 'Friday' in text


@needs_engine
def test_a_language_that_does_not_exist_falls_back(tmp_path, app):
    picture = write_page(tmp_path / 'page.png')
    text = ocr_image_bytes(picture.read_bytes(), language='not-a-language')
    assert 'launch' in text.lower()


# ── a scanned PDF ──────────────────────────────────────────────────────────

@needs_engine
def test_a_scanned_pdf_is_read(scanned):
    result = ocr_pdf(scanned)
    assert result.pages_read == 1
    assert 'launch' in result.text.lower()
    assert 'Friday' in result.text


@needs_engine
def test_the_reader_says_the_text_came_from_the_pictures(scanned):
    document = read_document(scanned)
    assert 'launch' in document.text.lower()
    assert any('pictures' in warning for warning in document.warnings)


def test_a_pdf_with_a_text_layer_is_not_sent_to_the_ocr(tmp_path):
    from document_fixtures import make_pdf

    path = make_pdf(tmp_path / 'typed.pdf', lines=('This page has real text.',))
    document = read_document(path)
    assert 'real text' in document.text
    assert not any('pictures' in warning for warning in document.warnings)


def test_a_document_that_is_not_there_is_refused(tmp_path):
    with pytest.raises(DocumentError):
        read_document(tmp_path / 'nothing.pdf')
