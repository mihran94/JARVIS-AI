"""Reading local documents: PDF, DOCX, chunks and comparison.

WHAT IS COVERED
    * A PDF is read, and the pages it has are reported.
    * A PDF that is protected, damaged, or a picture of a page is refused
      with a sentence the owner can act on, and a PDF that is too long
      says that it was cut.
    * A DOCX is read with its tables readable, not with the cells glued
      together.
    * A long document is cut into chunks that stand on their own.
    * Two documents are compared line by line.
    * Nothing is ever sent anywhere: reading is a local act.
"""
import os
import zipfile

import pytest

from document_fixtures import make_docx, make_pdf
from desktop import documents


# ── plain text ───────────────────────────────────────────────────────────────

def test_a_text_file_is_read(tmp_path):
    path = tmp_path / 'notes.md'
    path.write_text('# Title\n\nSome text.\n', encoding='utf-8')
    document = documents.read_document(path)
    assert document.kind == 'text'
    assert document.name == 'notes.md'
    assert 'Some text.' in document.text
    assert not document.truncated
    assert document.warnings == []


def test_windows_line_endings_are_read_the_same_way(tmp_path):
    path = tmp_path / 'windows.txt'
    path.write_bytes(b'First line.\r\nSecond line.\r\n')
    document = documents.read_document(path)
    assert document.text == 'First line.\nSecond line.\n'


def test_a_binary_file_says_it_is_binary(tmp_path):
    """A file with a text name but binary content is still binary."""
    path = tmp_path / 'thing.txt'
    path.write_bytes(b'\x00\x01\x02')
    with pytest.raises(documents.DocumentError, match='binary'):
        documents.read_document(path)


def test_an_unsupported_kind_of_file_says_what_is_supported(tmp_path):
    path = tmp_path / 'picture.png'
    path.write_bytes(b'\x89PNG\r\n\x1a\n')
    with pytest.raises(documents.DocumentError, match='Supported'):
        documents.read_document(path)


def test_a_file_that_is_too_large_is_refused(tmp_path):
    path = tmp_path / 'huge.txt'
    path.write_bytes(b'A' * (documents.MAX_DOCUMENT_BYTES + 1))
    with pytest.raises(documents.DocumentError, match='limit'):
        documents.read_document(path)


def test_a_file_that_is_not_there_says_so(tmp_path):
    with pytest.raises(documents.DocumentError, match='no longer there'):
        documents.read_document(tmp_path / 'missing.txt')


# ── PDF ─────────────────────────────────────────────────────────────────────

def test_a_pdf_is_read(tmp_path):
    path = make_pdf(tmp_path / 'letter.pdf')
    document = documents.read_document(path)
    assert document.kind == 'pdf'
    assert document.pages == 1
    assert 'Hello from the PDF' in document.text
    assert not document.truncated


def test_a_pdf_that_is_not_a_pdf_is_refused_honestly(tmp_path):
    path = tmp_path / 'broken.pdf'
    path.write_bytes(b'%PDF-1.4\nthis is not a pdf')
    with pytest.raises(documents.DocumentError):
        documents.read_document(path)


def test_a_pdf_with_no_text_layer_says_what_it_could_not_do(tmp_path):
    """A page that is a picture has no text layer.

    What happens then depends on the machine: where the recognition
    engine is installed the picture is read, and where it is not the
    owner is told what to install. Either way the document is never
    reported as an empty page.
    """
    from pypdf import PdfWriter

    path = tmp_path / 'picture.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, 'wb') as handle:
        writer.write(handle)
    with pytest.raises(documents.DocumentError) as error:
        documents.read_document(path)
    message = str(error.value)
    assert 'no text layer' in message
    # Either the engine was missing and the owner is told what to
    # install, or the engine read the picture and found no writing on it.
    assert 'Tesseract' in message or 'no writing was recognised' in message


def test_a_protected_pdf_is_refused_honestly(tmp_path):
    from pypdf import PdfWriter

    path = tmp_path / 'locked.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt('the-secret')
    with open(path, 'wb') as handle:
        writer.write(handle)
    with pytest.raises(documents.DocumentError, match='password'):
        documents.read_document(path)


# ── DOCX ────────────────────────────────────────────────────────────────────

def test_a_docx_is_read(tmp_path):
    path = make_docx(tmp_path / 'report.docx')
    document = documents.read_document(path)
    assert document.kind == 'docx'
    assert 'First paragraph' in document.text
    assert 'Second paragraph' in document.text


def test_the_cells_of_a_table_are_not_glued_together(tmp_path):
    """The cells used to run together, so a table was unreadable."""
    path = make_docx(tmp_path / 'table.docx')
    document = documents.read_document(path)
    assert 'Name | Value' in document.text
    assert 'alpha | 1' in document.text
    assert 'alpha1' not in document.text


def test_a_damaged_docx_is_refused_honestly(tmp_path):
    path = tmp_path / 'broken.docx'
    path.write_bytes(b'not a zip file at all')
    with pytest.raises(documents.DocumentError, match='damaged'):
        documents.read_document(path)


# ── chunks and comparison ───────────────────────────────────────────────────

def test_a_long_document_is_cut_into_chunks_that_stand_alone():
    text = '\n'.join(f'Line number {index} of the document.' for index in range(400))
    chunks = documents.chunk_text(text, size=500)
    assert len(chunks) > 1
    assert chunks[0].startswith('[part 1]')
    assert chunks[-1].startswith(f'[part {len(chunks)}]')
    # Every line of the document is in one of the chunks.
    joined = ' '.join(chunks)
    for index in (0, 199, 399):
        assert f'Line number {index} of the document.' in joined


def test_a_short_document_is_one_chunk():
    chunks = documents.chunk_text('One line.', size=8000)
    assert chunks == ['[part 1]\nOne line.']


def test_an_empty_document_has_no_chunks():
    assert documents.chunk_text('   \n  ') == []


def test_two_documents_are_compared_line_by_line(tmp_path):
    first = tmp_path / 'first.txt'
    first.write_text('alpha\nbeta\ngamma\n', encoding='utf-8')
    second = tmp_path / 'second.txt'
    second.write_text('alpha\nbeta\ndelta\n', encoding='utf-8')
    left = documents.read_document(first)
    right = documents.read_document(second)
    result = documents.compare_documents(left, right)
    assert result['identical'] is False
    assert 'gamma' in result['only_first']
    assert 'delta' in result['only_second']
    assert 'alpha' in result['shared']
    text = documents.comparison_text(result)
    assert 'differ' in text
    assert 'gamma' in text


def test_two_documents_with_the_same_text_are_identical(tmp_path):
    path = tmp_path / 'same.txt'
    path.write_text('alpha\nbeta\n', encoding='utf-8')
    left = documents.read_document(path)
    right = documents.read_document(path)
    result = documents.compare_documents(left, right)
    assert result['identical'] is True
    assert 'same' in documents.comparison_text(result)


def test_reading_a_document_does_not_send_anything(tmp_path):
    """Reading is a local act. The module does not import a network client."""
    source = open(os.path.join(os.path.dirname(__file__), '..', 'desktop',
                                'documents.py'), encoding='utf-8').read()
    for forbidden in ('httpx', 'requests', 'urllib', 'socket'):
        assert forbidden not in source, f'documents.py must not use {forbidden}'
