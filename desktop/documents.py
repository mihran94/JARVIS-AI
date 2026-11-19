"""Reading local documents for the Files & Folders workspace.

WHAT THIS IS FOR
    The workspace could show UTF-8 text, code and a little DOCX. A PDF
    was refused outright, and a DOCX was read as a run of paragraphs with
    the table cells glued together. This reads documents properly enough
    to preview them, compare two of them and put one in front of the
    assistant.

WHAT THIS WILL NOT DO
    * It never sends anything anywhere. Reading a document is a local
      act; the owner still has to agree before any of its text reaches a
      provider.
    * It never scans the computer. It reads the files the owner chose.
    * It does not do OCR. A PDF whose pages are pictures has no text to
      read, and this says so instead of pretending the page was empty
      because the page was empty.

LIMITS
    Every limit is bounded, so a huge or hostile document cannot take the
    application down:

        a document is at most 8 MiB
        a PDF is read for at most 400 pages
        the text of one document is at most 400,000 characters
        a chunk handed to the assistant is at most 8,000 characters

    When a limit is reached the document says so, so the owner is never
    shown a part of a document and told it is the whole thing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree

#: The largest document that is opened at all.
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024

#: The largest number of pages of a PDF that are read.
MAX_PDF_PAGES = 400

#: The largest amount of text one document may yield.
MAX_TEXT_CHARACTERS = 400_000

#: The size of one chunk of a document.
CHUNK_CHARACTERS = 8_000

#: The suffixes this module knows how to read.
TEXT_SUFFIXES = frozenset({
    '.txt', '.md', '.markdown', '.csv', '.json', '.py', '.js', '.ts',
    '.jsx', '.tsx', '.html', '.css', '.xml', '.yaml', '.yml', '.toml',
    '.log', '.ini', '.java', '.kt', '.sql', '.sh', '.ps1', '.bat', '.cmd',
    '.rst',
})
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | {'.docx', '.pdf'}

_WORD_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


class DocumentError(ValueError):
    """A document could not be read."""


@dataclass
class Document:
    """One document, read into memory."""

    name: str
    text: str
    kind: str = 'text'
    pages: int = 0
    truncated: bool = False
    warnings: list = field(default_factory=list)

    @property
    def characters(self) -> int:
        return len(self.text)

    def as_dict(self) -> dict:
        return {
            'name': self.name,
            'kind': self.kind,
            'pages': self.pages,
            'characters': self.characters,
            'truncated': self.truncated,
            'warnings': list(self.warnings),
        }


def _normalise_newlines(text: str) -> str:
    return text.replace('\r\n', '\n').replace('\r', '\n')


def _clip(text: str, warnings: list) -> tuple:
    """Cut the text at the limit and say so when it is cut."""
    if len(text) <= MAX_TEXT_CHARACTERS:
        return text, False
    warnings.append(
        f'The document is longer than {MAX_TEXT_CHARACTERS:,} characters, so only '
        'the first part was read.')
    return text[:MAX_TEXT_CHARACTERS], True


def _read_text(path: Path) -> tuple:
    """The text of a plain UTF-8 file."""
    raw = path.read_bytes()
    if b'\x00' in raw:
        raise DocumentError('This looks like a binary file, so there is no text to read.')
    try:
        return _normalise_newlines(raw.decode('utf-8-sig'))
    except UnicodeError:
        raise DocumentError(
            'This file is not UTF-8 text. Windows text files are usually UTF-8 now, '
            'so this one is saved in another encoding.') from None


def _docx_text(path: Path) -> str:
    """The text of a DOCX, with the tables readable.

    The paragraphs and the tables live in the same part of the file. A
    paragraph inside a table is read as one line, so the cells used to be
    glued together; a table is now read row by row with the cells
    separated, which is what the owner sees in Word.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo('word/document.xml')
            if info.file_size > 16 * 1024 * 1024:
                raise DocumentError('This DOCX is too large to read.')
            data = archive.read(info)
    except KeyError:
        raise DocumentError('This DOCX has no document part, so it cannot be read.') from None
    except zipfile.BadZipFile:
        raise DocumentError('This DOCX is damaged, so it cannot be read.') from None
    except (OSError, RuntimeError) as error:
        raise DocumentError(f'This DOCX could not be read: {error}') from None
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        raise DocumentError('This DOCX is damaged, so it cannot be read.') from None

    lines = []

    def paragraph_text(node) -> str:
        return ''.join(element.text or '' for element in node.iter(_WORD_NS + 't'))

    def walk(node) -> None:
        for child in node:
            if child.tag == _WORD_NS + 'p':
                text = paragraph_text(child)
                if text.strip():
                    lines.append(text)
            elif child.tag == _WORD_NS + 'tbl':
                for row in child.findall(_WORD_NS + 'tr'):
                    cells = []
                    for cell in row.findall(_WORD_NS + 'tc'):
                        cells.append(' '.join(
                            paragraph_text(p).strip() for p in cell.findall(_WORD_NS + 'p')).strip())
                    if any(cells):
                        lines.append(' | '.join(cells))
                lines.append('')
            else:
                walk(child)

    walk(root)
    return '\n'.join(lines)


def _pdf_text(path: Path, warnings: list) -> tuple:
    """The text of a PDF, and the number of pages it has."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise DocumentError(
            'Reading PDF files needs the pypdf package, which is not installed.') from None
    try:
        reader = PdfReader(str(path))
    except Exception as error:
        raise DocumentError(f'This PDF could not be opened: {error}') from None
    if reader.is_encrypted:
        # An empty password unlocks a PDF whose only protection is "do not
        # print". A PDF with a real password stays locked.
        try:
            if reader.decrypt('') == 0:
                raise DocumentError(
                    'This PDF is protected by a password, so it cannot be read. '
                    'Remove the protection and read it again.')
        except DocumentError:
            raise
        except Exception:
            raise DocumentError(
                'This PDF is protected by a password, so it cannot be read. '
                'Remove the protection and read it again.') from None
        warnings.append('This PDF was protected against printing only.')
    try:
        pages = len(reader.pages)
    except Exception as error:
        raise DocumentError(f'This PDF is damaged, so it cannot be read: {error}') from None
    wanted = min(pages, MAX_PDF_PAGES)
    if pages > MAX_PDF_PAGES:
        warnings.append(
            f'This PDF has {pages} pages, so only the first {MAX_PDF_PAGES} were read.')
    parts = []
    for index in range(wanted):
        try:
            page = reader.pages[index]
            text = page.extract_text() or ''
        except Exception as error:
            warnings.append(f'Page {index + 1} could not be read: {error}')
            continue
        if text.strip():
            parts.append(text)
    body = '\n'.join(parts)
    if pages and not body.strip():
        raise DocumentError(
            'This PDF has no text layer: its pages are pictures. Reading pictures '
            'of text is not supported yet, so there is nothing to read.')
    return body, pages


def read_document(path: str | Path, *, name: str = '') -> Document:
    """Read one document the owner chose.

    Raises `DocumentError` with a sentence the owner can act on when the
    document cannot be read.
    """
    source = Path(path).expanduser()
    label = name or source.name
    if not source.is_file():
        raise DocumentError('This file is no longer there.')
    try:
        size = source.stat().st_size
    except OSError as error:
        raise DocumentError(f'This file could not be read: {error}') from None
    if size > MAX_DOCUMENT_BYTES:
        raise DocumentError(
            f'This file is {size:,} bytes, which is over the {MAX_DOCUMENT_BYTES:,} '
            'byte limit for reading a document.')
    suffix = source.suffix.casefold()
    if suffix not in SUPPORTED_SUFFIXES:
        supported = ', '.join(sorted(SUPPORTED_SUFFIXES))
        raise DocumentError(
            f'This kind of file cannot be read. Supported: {supported}. '
            'PDF, DOCX, Markdown, text, code, CSV and JSON.')
    warnings: list = []
    if suffix == '.pdf':
        text, pages = _pdf_text(source, warnings)
        kind = 'pdf'
    elif suffix == '.docx':
        text = _docx_text(source)
        pages = 0
        kind = 'docx'
    else:
        text = _read_text(source)
        pages = 0
        kind = 'text'
    text = _normalise_newlines(text)
    if not text.strip():
        raise DocumentError('This document has no readable text.')
    text, truncated = _clip(text, warnings)
    return Document(name=label, text=text, kind=kind, pages=pages,
                    truncated=truncated, warnings=warnings)


def chunk_text(text: str, size: int = CHUNK_CHARACTERS) -> list:
    """Split a long text into chunks that each stand on their own.

    The split is made on a line boundary when there is one nearby, so a
    chunk does not start in the middle of a paragraph. Every chunk is
    labelled with its position, so the assistant can say which part it
    is answering from.
    """
    if size <= 0:
        raise ValueError('The chunk size must be positive.')
    if not text or not text.strip():
        return []
    chunks = []
    position = 1
    rest = text
    while rest:
        if len(rest) <= size:
            piece = rest
            rest = ''
        else:
            window = rest[:size]
            cut = window.rfind('\n')
            if cut < size // 2:
                cut = window.rfind(' ')
            if cut <= 0:
                cut = size
            piece = rest[:cut]
            rest = rest[cut:].lstrip('\n')
        label = f'[part {position}]'
        chunks.append(f'{label}\n{piece.strip()}')
        position += 1
    return chunks


_LINE = re.compile(r'^\s*$')


def compare_documents(first: Document, second: Document) -> dict:
    """Compare two documents, line by line.

    The result names the lines only in the first, the lines only in the
    second and the lines both share. It is a comparison of the text the
    owner chose; it does not say what the documents mean.
    """
    def lines(document: Document) -> list:
        return [line.strip() for line in document.text.splitlines() if line.strip()]

    left, right = lines(first), lines(second)
    right_set = set(right)
    left_set = set(left)
    only_first = [line for line in left if line not in right_set]
    only_second = [line for line in right if line not in left_set]
    shared = [line for line in left if line in right_set]
    return {
        'first': first.name,
        'second': second.name,
        'first_lines': len(left),
        'second_lines': len(right),
        'shared': shared,
        'only_first': only_first,
        'only_second': only_second,
        'identical': not only_first and not only_second,
    }


def comparison_text(result: dict, limit: int = 120) -> str:
    """The comparison as text, for the owner to read."""
    if result['identical']:
        return (f'{result["first"]} and {result["second"]} have the same {result["first_lines"]} '
                'lines of text.')
    parts = [f'{result["first"]} and {result["second"]} differ.',
             f'{len(result["shared"])} lines are in both.',
             f'{len(result["only_first"])} lines are only in {result["first"]}.',
             f'{len(result["only_second"])} lines are only in {result["second"]}.']
    for title, rows in (('Only in ' + result['first'], result['only_first']),
                        ('Only in ' + result['second'], result['only_second'])):
        if rows:
            parts.append(title + ':')
            parts.extend('  ' + row for row in rows[:limit])
            if len(rows) > limit:
                parts.append(f'  ... and {len(rows) - limit} more')
    return '\n'.join(parts)
