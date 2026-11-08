"""UTF-8 editor storage with path confinement, atomic writes and revision backups."""
import ast
import hashlib
from pathlib import Path
import os
import re
import tempfile
import uuid


class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name):
        normalized = name.replace(chr(92), '/')
        parts = normalized.split('/')
        reserved = {'CON','PRN','AUX','NUL',
                    *[f'COM{i}' for i in range(1,10)], *[f'LPT{i}' for i in range(1,10)]}
        if (not name or normalized.startswith('/') or ':' in name or
                any(p in ('', '.', '..') or p.startswith('.') or p.endswith((' ', '.'))
                    or any(c in '<>"|?*' or ord(c) < 32 for c in p)
                    or p.split('.')[0].upper() in reserved for p in parts)):
            raise ValueError('Use a normal relative filename inside the workspace.')
        path = self.root.joinpath(*parts)
        if not path.resolve().is_relative_to(self.root):
            raise ValueError('Path leaves the workspace.')
        return path

    def read(self, name):
        path = self.path(name)
        if path.stat().st_size > 1_000_000:
            raise ValueError('Editor file limit is 1 MB.')
        return path.read_text(encoding='utf-8')

    def save(self, name, content):
        data = content.encode('utf-8')
        if len(data) > 1_000_000:
            raise ValueError('Editor file limit is 1 MB.')
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup = self.root / '.revisions'
            backup.mkdir(exist_ok=True)
            if backup.is_symlink() or not backup.resolve().is_relative_to(self.root):
                raise ValueError('Unsafe revision directory.')
            (backup / (uuid.uuid4().hex + '.bak')).write_bytes(path.read_bytes())
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.jarvis-')
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return f'Saved {name}; previous contents backed up if the file existed.'

    @staticmethod
    def digest(content):
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    @staticmethod
    def check_python(content):
        ast.parse(content)
        return 'Python syntax is valid. Code was not executed.'
