"""Reading the text out of a picture of a document.

WHAT THIS IS
    A PDF that was scanned is a picture of a page, not text. It has no
    text layer, so a document reader finds nothing in it and the owner is
    told the page is empty, when the page is not empty at all.

    This module reads that picture: the pages are rasterised and the
    text is recognised **on this computer**. Nothing is uploaded, and no
    network service is involved.

    The recognition engine is **Tesseract**, which is optional. When it
    is not installed, every entry point says so and says what to
    install, rather than quietly returning an empty page. That is the
    difference between "this page has no text" and "this page has text
    I could not read yet".

WHAT THIS IS NOT
    * It is not a cloud OCR service. The engine runs here.
    * It is not a general image reader. It reads a page of a document.
    * It does not guess. A page that holds no recognisable text says so.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import subprocess

#: The languages the owner can choose.
OCR_LANGUAGES = ('eng', 'tam', 'fra', 'deu', 'spa', 'ara', 'hin', 'mal')

#: How many pages of one document are read at most.
MAX_OCR_PAGES = 40

#: How long the engine may take for one page, in seconds.
OCR_TIMEOUT = 90

#: The largest image the engine is given, in pixels on the long side.
MAX_IMAGE_EDGE = 2600

#: What the owner is told when the engine is not installed.
MISSING_ENGINE = (
    'Tesseract OCR is not installed, so the text in a scanned page cannot be read. '
    'Install Tesseract, put it on the PATH and restart JARVIS. The page itself is '
    'not lost; it is only unreadable until the engine is there.')


class OcrUnavailable(RuntimeError):
    """The recognition engine is not installed or could not be started."""


@dataclass
class OcrResult:
    """What was read out of a document."""

    text: str = ''
    pages_read: int = 0
    pages_total: int = 0
    language: str = 'eng'
    engine: str = ''
    truncated: bool = False
    message: str = ''

    def as_dict(self) -> dict:
        return {'text': self.text, 'pages_read': self.pages_read,
                'pages_total': self.pages_total, 'language': self.language,
                'engine': self.engine, 'truncated': self.truncated,
                'message': self.message}


def tesseract_executable() -> str:
    """The Tesseract binary, or a refusal that says how to get it."""
    found = shutil.which('tesseract')
    if found:
        return found
    if os.name == 'nt':
        for base in (r'C:\Program Files\Tesseract-OCR', r'C:\Program Files (x86)\Tesseract-OCR'):
            candidate = Path(base) / 'tesseract.exe'
            if candidate.is_file():
                return str(candidate)
    raise OcrUnavailable(MISSING_ENGINE)


def engine_version(executable: str) -> str:
    """The version of the engine, for the report."""
    try:
        result = subprocess.run([executable, '--version'], capture_output=True, text=True,
                                timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return ''
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else ''


def ocr_image_bytes(data: bytes, *, language: str = 'eng',
                    timeout: int = OCR_TIMEOUT) -> str:
    """The text in a picture, recognised on this computer."""
    executable = tesseract_executable()
    if language not in OCR_LANGUAGES:
        language = 'eng'
    try:
        result = subprocess.run([executable, 'stdin', 'stdout', '-l', language],
                                input=data, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise OcrUnavailable('The text reading took too long and was stopped.') from None
    except (OSError, subprocess.SubprocessError):
        raise OcrUnavailable('The text reading engine could not be started.') from None
    if result.returncode != 0:
        detail = result.stderr.decode('utf-8', 'replace').strip()
        raise OcrUnavailable(
            'The text reading engine could not read that page.'
            + (f' {detail[:200]}' if detail else ''))
    return result.stdout.decode('utf-8', 'replace').strip()


def ocr_image_file(path, *, language: str = 'eng', timeout: int = OCR_TIMEOUT) -> str:
    """The text in a picture file."""
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise OcrUnavailable(f'The picture could not be read. {error}') from None
    return ocr_image_bytes(data, language=language, timeout=timeout)


def pdf_page_count(path) -> int:
    """How many pages a PDF has."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise OcrUnavailable('The PDF reader is not installed.') from None
    try:
        return len(PdfReader(str(path)).pages)
    except Exception as error:
        raise OcrUnavailable(f'The PDF could not be opened. {error}') from None


def pdf_page_images(path, *, max_pages: int = MAX_OCR_PAGES, scale: float = 2.0) -> list:
    """The pages of a PDF as pictures.

    The pages are drawn with the PDF engine that is already part of the
    Qt runtime, so a scanned document does not need a second program
    installed to be read.
    """
    try:
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QImage
        from PySide6.QtPdf import QPdfDocument
    except ImportError as error:
        raise OcrUnavailable(f'The PDF engine is not available. {error}') from None

    document = QPdfDocument()
    document.load(str(path))
    if document.status() != QPdfDocument.Status.Ready:
        raise OcrUnavailable('The PDF could not be opened for reading.')
    total = document.pageCount()
    images = []
    for index in range(min(total, max_pages)):
        size = document.pagePointSize(index)
        if size.isEmpty():
            continue
        target = QSize(int(size.width() * scale), int(size.height() * scale))
        image = document.render(index, target)
        if image.isNull():
            continue
        images.append(image)
    return images


def _image_bytes(image) -> bytes:
    """A Qt image as PNG bytes."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    try:
        if not image.save(buffer, 'PNG'):
            return b''
    finally:
        buffer.close()
    return bytes(data)


def ocr_pdf(path, *, language: str = 'eng', max_pages: int = MAX_OCR_PAGES) -> OcrResult:
    """The text of a scanned PDF, read on this computer.

    A PDF that already has a text layer is not sent here: the document
    reader reads that itself. This is for the picture of a page.
    """
    source = Path(path)
    if not source.is_file():
        raise OcrUnavailable('The document is not there.')
    executable = tesseract_executable()
    total = pdf_page_count(source)
    images = pdf_page_images(source, max_pages=max_pages)
    pages = []
    for image in images:
        text = ocr_image_bytes(_image_bytes(image), language=language)
        if text:
            pages.append(text)
    result = OcrResult(
        text='\n\n'.join(pages),
        pages_read=len(images),
        pages_total=total,
        language=language,
        engine=engine_version(executable),
        truncated=total > len(images),
        message=(f'The text of {len(images)} of {total} page(s) was read on this computer.'
                 if total else ''))
    if not result.text:
        result.message = ('No text was recognised in those pages. The page may be a '
                          'picture without writing on it.')
    return result


__all__ = ['MAX_OCR_PAGES', 'MISSING_ENGINE', 'OCR_LANGUAGES', 'OcrResult',
           'OcrUnavailable', 'engine_version', 'ocr_image_bytes', 'ocr_image_file',
           'ocr_pdf', 'pdf_page_count', 'pdf_page_images', 'tesseract_executable']
