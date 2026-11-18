"""Searching inside the folders the owner has approved.

WHAT THIS IS FOR
    The Files & Folders workspace can read one document. When a folder
    holds a hundred of them, the owner needs to find the one they mean
    before anything is read into the conversation.

WHAT IT DOES
    * It searches the text of the files in ONE folder the owner chose,
      and says which file and which line matched.
    * It skips the files that are not text: binaries, files that look
      like secrets, and the files the project's own `.gitignore` keeps
      out.
    * It is bounded, so a huge folder cannot take the application down,
      and it says when it did not look at everything.

WHAT IT WILL NOT DO
    * It never searches the whole computer. Only the folder the owner
      chose, and only its own top level.
    * It never sends anything anywhere. The search happens here.
    * It never opens a file to search it: the file is read as bytes and
      decoded, so nothing is executed and nothing is opened in another
      program.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.protection import SKIP_DIRS, Protection

#: The most files that are searched in one folder.
MAX_FILES = 400

#: The largest file that is searched.
MAX_FILE_BYTES = 1024 * 1024

#: The most matches that are reported.
MAX_MATCHES = 60

#: The most characters of a line that are reported.
MAX_LINE = 200

#: The suffixes that are searched. Everything else is skipped, because
#: it is not text.
TEXT_SUFFIXES = frozenset({
    '.txt', '.md', '.markdown', '.rst', '.csv', '.tsv', '.json', '.yaml',
    '.yml', '.toml', '.ini', '.cfg', '.conf', '.log', '.py', '.js', '.jsx',
    '.ts', '.tsx', '.java', '.kt', '.c', '.h', '.cpp', '.cs', '.go', '.rs',
    '.rb', '.php', '.swift', '.sh', '.ps1', '.bat', '.cmd', '.html', '.css',
    '.xml', '.sql', '.gradle',
})


@dataclass
class Match:
    """One place where the search text was found."""

    path: str
    line: int
    text: str

    def as_dict(self) -> dict:
        return {'path': self.path, 'line': self.line, 'text': self.text}


@dataclass
class SearchResult:
    """What the search found."""

    folder: str
    query: str = ''
    files_searched: int = 0
    files_skipped: int = 0
    matches: list = field(default_factory=list)
    truncated: bool = False

    @property
    def match_count(self) -> int:
        return len(self.matches)

    @property
    def files_with_matches(self) -> list:
        seen = []
        for match in self.matches:
            if match.path not in seen:
                seen.append(match.path)
        return seen

    def as_dict(self) -> dict:
        return {
            'folder': self.folder, 'query': self.query,
            'files_searched': self.files_searched,
            'files_skipped': self.files_skipped,
            'matches': [match.as_dict() for match in self.matches],
            'truncated': self.truncated,
        }


def _decodable(raw: bytes) -> str | None:
    """The text of a file, or None when it is not text."""
    if b'\x00' in raw[:8192]:
        return None
    try:
        return raw.decode('utf-8-sig')
    except UnicodeError:
        return None


def search_folder(folder, query: str, *, limit: int = MAX_FILES) -> SearchResult:
    """Search the text of the files in one folder the owner chose."""
    root = Path(folder).expanduser()
    result = SearchResult(folder=str(root), query=str(query or ''))
    if not root.is_dir():
        return result
    needle = str(query or '').strip().casefold()
    if not needle:
        return result
    protection = Protection(root)
    searched = 0
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name.casefold())
    except OSError:
        return result
    for entry in entries:
        if searched >= limit:
            result.truncated = True
            break
        if entry.is_symlink() or not entry.is_file():
            continue
        relative = entry.name
        if protection.blocked(relative):
            result.files_skipped += 1
            continue
        if entry.suffix.casefold() not in TEXT_SUFFIXES:
            result.files_skipped += 1
            continue
        try:
            if entry.stat().st_size > MAX_FILE_BYTES:
                result.files_skipped += 1
                continue
            raw = entry.read_bytes()
        except OSError:
            result.files_skipped += 1
            continue
        text = _decodable(raw)
        if text is None:
            result.files_skipped += 1
            continue
        searched += 1
        result.files_searched += 1
        for number, line in enumerate(text.splitlines(), 1):
            if needle in line.casefold():
                result.matches.append(Match(relative, number, line.strip()[:MAX_LINE]))
                if len(result.matches) >= MAX_MATCHES:
                    result.truncated = True
                    break
        if len(result.matches) >= MAX_MATCHES:
            break
    return result


def search_result_text(result: SearchResult) -> str:
    """The search result as the owner reads it."""
    if not result.query:
        return 'Nothing was searched for.'
    if not result.files_searched and not result.files_skipped:
        return f'{result.folder} could not be searched.'
    lines = [f'"{result.query}" was found {result.match_count} time(s) in '
             f'{len(result.files_with_matches)} of {result.files_searched} file(s) '
             f'searched in {result.folder}.']
    for match in result.matches[:MAX_MATCHES]:
        lines.append(f'  {match.path}:{match.line} — {match.text}')
    if result.files_skipped:
        lines.append(f'{result.files_skipped} file(s) were not searched, because they '
                     'are not text, hold secrets, or the project keeps them out.')
    if result.truncated:
        lines.append('There was more to search than one run covers, so some was left out.')
    return '\n'.join(lines)


def summary_export(text: str, *, title: str = 'JARVIS summary') -> str:
    """The summary as a document the owner can save.

    The text is written as it is. Nothing is added to it that JARVIS did
    not write, and the date it was made is on it, so a summary that is
    read later says when it was written.
    """
    from datetime import datetime

    stamp = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')
    body = (text or '').strip()
    return f'# {title}\n\nWritten by JARVIS on {stamp}.\n\n{body}\n'
