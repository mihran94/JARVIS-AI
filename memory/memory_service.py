"""Local notes and keyword search in the desktop history database."""
from __future__ import annotations

import math
import unicodedata
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

#: The words that are too common to be worth searching for.
STOP_WORDS = frozenset("""
a an and are as at be but by for from has have how in is it its of on or that
the this to was were what when where which who will with you your is't
""".split())

#: The words that mean a search found nothing, whatever the language.
_EMPTY_WORDS = frozenset({'the', 'and', 'for', 'with', 'that', 'this', 'from',
                          'have', 'has', 'was', 'were', 'not', 'but', 'you',
                          'your', 'what', 'when', 'where', 'which', 'who',
                          'will', 'can', 'are', 'des', 'les', 'une', 'pour',
                          'dans', 'que', 'qui', 'avec', 'sur', 'est'})


def tokenize(text: str) -> list[str]:
    """The words of a text, in lower case, without the very common ones."""
    if not text:
        return []
    normalized = unicodedata.normalize('NFC', text).casefold()
    words = ''.join(
        char if char.isalnum() or unicodedata.category(char).startswith('M') or char == "'" else ' '
        for char in normalized
    ).split()
    return [word for word in words if word not in STOP_WORDS and len(word) > 1]


def search_terms(query: str) -> list[str]:
    """The words of a query that mean something."""
    words = tokenize(query)
    return [word for word in words if word not in _EMPTY_WORDS]


@dataclass
class Memory:
    """One memory."""

    id: str
    title: str
    body: str
    tags: tuple = field(default_factory=tuple)
    created: str = ''

    def to_json(self) -> dict:
        return {'id': self.id, 'title': self.title, 'body': self.body,
                'tags': list(self.tags), 'created': self.created}


class MemoryError(RuntimeError):
    """A memory could not be written or read."""


class MemoryService:
    """Keeps and finds the owner's memories.

    The service owns its own table in the desktop history database.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS memories(
                    id TEXT PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP,
                    title TEXT NOT NULL, body TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '');
                CREATE INDEX IF NOT EXISTS memories_created ON memories(created);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    # --------------------------------------------------------------- writing

    def remember(self, title: str, body: str, tags=()) -> Memory:
        """Save a memory. The title may not be empty."""
        title = (title or '').strip()
        body = (body or '').strip()
        if not title:
            raise MemoryError('A memory needs a title.')
        if not body:
            raise MemoryError('A memory needs some text.')
        clean_tags = tuple(sorted({tag.strip().lower() for tag in tags if tag and tag.strip()}))
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO memories(id, title, body, tags) VALUES(?,?,?,?)',
                       (identifier, title, body, ','.join(clean_tags)))
            row = db.execute('SELECT created FROM memories WHERE id=?', (identifier,)).fetchone()
        return Memory(id=identifier, title=title, body=body, tags=clean_tags,
                      created=row['created'] if row else '')

    def forget(self, identifier: str) -> bool:
        """Delete a saved note."""
        with self.connect() as db:
            cursor = db.execute('DELETE FROM memories WHERE id=?', (identifier,))
            return cursor.rowcount > 0

    def update(self, identifier: str, title=None, body=None, tags=None) -> Memory:
        """Change a memory that is already there."""
        with self.connect() as db:
            row = db.execute('SELECT * FROM memories WHERE id=?', (identifier,)).fetchone()
            if row is None:
                raise MemoryError('That memory is not there.')
            new_title = (title if title is not None else row['title']).strip()
            new_body = (body if body is not None else row['body']).strip()
            if not new_title or not new_body:
                raise MemoryError('A memory needs a title and some text.')
            if tags is None:
                new_tags = row['tags']
            else:
                new_tags = ','.join(sorted({tag.strip().lower() for tag in tags if tag and tag.strip()}))
            db.execute('UPDATE memories SET title=?, body=?, tags=? WHERE id=?',
                       (new_title, new_body, new_tags, identifier))
        return Memory(id=identifier, title=new_title, body=new_body,
                      tags=tuple(tag for tag in new_tags.split(',') if tag),
                      created=row['created'])

    # --------------------------------------------------------------- reading

    def all(self, limit: int = 200) -> list:
        """Every memory, newest first."""
        with self.connect() as db:
            rows = db.execute('SELECT * FROM memories ORDER BY created DESC, id DESC LIMIT ?',
                              (int(limit),)).fetchall()
        return [self._to_memory(row) for row in rows]

    def get(self, identifier: str):
        """One memory, or None."""
        with self.connect() as db:
            row = db.execute('SELECT * FROM memories WHERE id=?', (identifier,)).fetchone()
        return self._to_memory(row) if row is not None else None

    def search(self, query: str, limit: int = 20) -> list:
        """The memories that match a query, the best one first.

        The scoring is BM25 over the title, the body and the tags. A memory
        that matches nothing is not returned, so an empty result really means
        "nothing found".
        """
        terms = dict.fromkeys(search_terms(query))
        if not terms:
            return []
        with self.connect() as db:
            rows = db.execute('SELECT * FROM memories').fetchall()
        if not rows:
            return []
        documents = []
        for row in rows:
            words = tokenize(row['title']) + tokenize(row['body']) * 2 + tokenize(row['tags']) * 2
            documents.append((self._to_memory(row), words))
        average = sum(len(words) for _, words in documents) / len(documents)
        total = len(documents)
        scored = []
        # How many memories carry each word. A word that is in many memories
        # tells less than a word that is in few.
        document_frequency = {term: sum(1 for _, words in documents if term in words)
                              for term in terms}
        for memory, words in documents:
            score = 0.0
            length = len(words) or 1
            for term in terms:
                frequency = words.count(term)
                if not frequency:
                    continue
                # The BM25 weight of a word. The log keeps the weight
                # positive even for a word that is in every memory.
                rarity = math.log(1 + (total - document_frequency[term] + 0.5)
                                  / (document_frequency[term] + 0.5))
                score += rarity * ((frequency * 2.2) / (frequency + 1.2 * (0.25 + 0.75 * length / max(average, 1))))
            if score > 0:
                scored.append((score, memory))
        scored.sort(key=lambda item: (-item[0], item[1].created))
        return [memory for _, memory in scored[:int(limit)]]

    def tags(self) -> list:
        """Every tag that is in use, with how many memories carry it."""
        counts = {}
        for memory in self.all(limit=10000):
            for tag in memory.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return sorted(counts.items())

    def as_context(self, query: str, limit: int = 4, max_characters: int = 1200) -> str:
        """The memories that match, as text for a prompt.

        This is what makes the memory useful to the assistant: the owner asks
        something, the matching memories are put in front of the provider,
        and nothing else is sent.
        """
        found = self.search(query, limit=limit)
        if not found:
            return ''
        lines = []
        used = 0
        for memory in found:
            piece = f'- {memory.title}: {memory.body}'
            remaining = max_characters - used
            if remaining <= 0:
                break
            lines.append(piece[:remaining])
            used += len(lines[-1]) + 1
        return '\n'.join(lines)

    @staticmethod
    def _to_memory(row) -> Memory:
        tags = tuple(tag for tag in (row['tags'] or '').split(',') if tag)
        return Memory(id=row['id'], title=row['title'], body=row['body'],
                      tags=tags, created=row['created'])
