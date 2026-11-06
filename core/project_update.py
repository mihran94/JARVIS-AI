"""Isolated ZIP editing sessions; never executes imported code."""
from pathlib import Path, PurePosixPath
import zipfile, tempfile, shutil, stat, difflib, os
from core.coding_workspace import ProjectWorkspace, _hidden, MAX_BYTES

class UpdateSession:
    def __init__(self, archive, destination):
        self.home = Path(tempfile.mkdtemp(prefix='jarvis-update-', dir=destination))
        self.root = self.home / 'project'
        self.root.mkdir()
        self.history = []
        self.skipped = []
        try:
            with zipfile.ZipFile(archive) as source:
                entries = source.infolist()
                if len(entries) > 5000 or sum(e.file_size for e in entries) > 100 * 1024 * 1024:
                    raise ValueError('ZIP exceeds 5000 entries or 100 MiB.')
                seen = set()
                for entry in entries:
                    name = entry.filename.rstrip('/')
                    parts = name.split('/')
                    if (not name or name.startswith('/') or '\\' in name or any(
                        p in ('', '.', '..') or ':' in p or p.endswith((' ', '.')) or
                        p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(10)],*[f'LPT{i}' for i in range(10)]}
                        for p in parts)):
                        raise ValueError('Unsafe ZIP path.')
                    if name.casefold() in seen or stat.S_ISLNK(entry.external_attr >> 16):
                        raise ValueError('Duplicate path or symbolic link in ZIP.')
                    seen.add(name.casefold())
                    if any(_hidden(p) for p in parts):
                        self.skipped.append(name)
                        continue
                    target = self.root.joinpath(*parts)
                    if entry.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with source.open(entry) as src, target.open('xb') as dst:
                            shutil.copyfileobj(src, dst)
            self.workspace = ProjectWorkspace(self.root)
        except Exception:
            shutil.rmtree(self.home)
            raise

    def preview(self, name, replacement):
        before = self.workspace.read_text(name)
        if len(replacement.encode('utf-8')) > MAX_BYTES or '\0' in replacement:
            raise ValueError('Replacement must be UTF-8 text under 128 KiB.')
        if str(name).endswith('.py'):
            compile(replacement, str(name), 'exec')
        raw = self.workspace._path(name).read_bytes()
        diff = ''.join(difflib.unified_diff(before.splitlines(True), replacement.splitlines(True), fromfile=str(name), tofile=str(name)+' (updated)'))
        return (str(name), raw, replacement.encode('utf-8'), diff)

    def apply(self, proposal):
        name, before, after, diff = proposal
        path = self.workspace._path(name)
        if path.read_bytes() != before:
            raise ValueError('File changed after preview. Preview again.')
        backup = self.home / f'backup-{len(self.history)}.bin'
        backup.write_bytes(before)
        self._write(path, after)
        self.history.append((name, backup, after))

    def _write(self, path, data):
        fd, tmp = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)

    def undo(self):
        if not self.history: raise ValueError('No change to undo in this session.')
        name, backup, after = self.history[-1]
        path = self.workspace._path(name)
        if path.read_bytes() != after: raise ValueError('File changed externally; undo refused.')
        self._write(path, backup.read_bytes())
        self.history.pop()

    def check(self):
        count = 0
        for path in self.root.rglob('*.py'):
            relative = path.relative_to(self.root)
            self.workspace._path(relative)
            compile(path.read_bytes(), str(relative), 'exec')
            count += 1
        return f'{count} Python files passed syntax checks. Runtime tests were not run.'

    def export(self, destination):
        destination = Path(destination).absolute()
        if destination.resolve().is_relative_to(self.home.resolve()):
            raise ValueError('Export outside the working copy.')
        with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as archive:
            for path in self.root.rglob('*'):
                relative = path.relative_to(self.root)
                self.workspace._path(relative)
                if path.is_file(): archive.write(path, relative.as_posix())
