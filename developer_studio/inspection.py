"""Looking at a project before anything is changed.

WHAT THIS IS FOR
    The developer flow has to say what it found before it asks a model to
    change anything: which project, what is wrong with it, and which
    files were looked at. Saying so needs the facts, not a guess.

WHAT IT FINDS
    * The shape of the project: the folders and the files at the top, how
      many files of each kind there are, and how big it is.
    * Errors that can be found without a model: a Python file that does
      not compile, and a JSON file that is not JSON. Those are real, they
      name the file and the line, and they can be checked.

WHAT IT WILL NOT DO
    * It never runs the project's code and never runs its tests. Those are
      the owner's call, and they happen later, through the approval
      gateway that already guards everything else.
    * It never changes anything.
    * It never reads a file that holds a secret, and never reads a file
      the project's own `.gitignore` keeps out. The rules for that live
      in `core.protection` and are the same ones the coding agent uses.
    * It is bounded: at most so many files, at most so deep, and at most
      so big a file. A project that is too big to look at says so
      instead of quietly reading a part of it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path

from core.protection import SKIP_DIRS, Protection

#: The most files that are looked at in one project.
MAX_FILES = 2000

#: The deepest folder that is looked at.
MAX_DEPTH = 8

#: The largest file that is read. A file bigger than this is counted but
#: not read, because reading it is not worth the memory.
MAX_FILE_BYTES = 512 * 1024

#: The most problems that are reported.
MAX_PROBLEMS = 50


@dataclass(frozen=True)
class Problem:
    """One real problem found in a project."""

    path: str
    kind: str
    message: str
    line: int = 0

    def as_dict(self) -> dict:
        return {'path': self.path, 'kind': self.kind, 'message': self.message,
                'line': self.line}

    def __str__(self) -> str:
        where = f'{self.path}:{self.line}' if self.line else self.path
        return f'{where} — {self.kind}: {self.message}'


@dataclass
class Inspection:
    """What was found in a project."""

    folder: str
    files_inspected: int = 0
    files_skipped: int = 0
    total_bytes: int = 0
    kinds: dict = field(default_factory=dict)
    top_level: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    truncated: bool = False

    @property
    def problem_count(self) -> int:
        return len(self.problems)

    def as_dict(self) -> dict:
        return {
            'folder': self.folder,
            'files_inspected': self.files_inspected,
            'files_skipped': self.files_skipped,
            'total_bytes': self.total_bytes,
            'kinds': dict(self.kinds),
            'top_level': list(self.top_level),
            'problems': [problem.as_dict() for problem in self.problems],
            'notes': list(self.notes),
            'truncated': self.truncated,
        }

    def summary(self) -> str:
        """The report the owner reads."""
        lines = [f'{self.files_inspected} file(s) looked at in {self.folder}.']
        if self.truncated:
            lines.append('The project is larger than the limit, so only part of it was '
                         'looked at.')
        if self.files_skipped:
            lines.append(f'{self.files_skipped} file(s) were not looked at, because they '
                         'hold secrets or the project keeps them out.')
        if self.kinds:
            kinds = ', '.join(f'{count} {kind}' for kind, count in
                              sorted(self.kinds.items(), key=lambda pair: -pair[1]))
            lines.append('Files: ' + kinds + '.')
        if self.top_level:
            lines.append('Top level: ' + ', '.join(self.top_level[:24]) +
                         ('…' if len(self.top_level) > 24 else '') + '.')
        if self.problems:
            lines.append(f'{len(self.problems)} problem(s) found:')
            for problem in self.problems[:MAX_PROBLEMS]:
                lines.append('  ' + str(problem))
            if len(self.problems) > MAX_PROBLEMS:
                lines.append(f'  … and {len(self.problems) - MAX_PROBLEMS} more')
        else:
            lines.append('No problem that can be found without running the code was found.')
        for note in self.notes:
            lines.append(note)
        return '\n'.join(lines)

    def problems_text(self, limit: int = 20) -> str:
        """The problems on their own, for the prompt of a coding model."""
        if not self.problems:
            return ''
        lines = [f'{problem.path}: {problem.kind}: {problem.message}'
                 for problem in self.problems[:limit]]
        if len(self.problems) > limit:
            lines.append(f'… and {len(self.problems) - limit} more')
        return '\n'.join(lines)


def _kind_of(path: Path) -> str:
    """What kind of file this is, in words the owner would use."""
    suffix = path.suffix.casefold()
    if not suffix:
        return 'file'
    return suffix.lstrip('.')


def _check_python(path: Path, relative: str) -> list:
    """The syntax errors of one Python file."""
    try:
        source = path.read_text('utf-8', errors='replace')
    except OSError:
        return []
    try:
        compile(source, str(path), 'exec')
    except SyntaxError as error:
        return [Problem(relative, 'python syntax',
                        (error.msg or 'the file does not compile').strip(),
                        error.lineno or 0)]
    except ValueError as error:
        # A source file with a null byte, for example.
        return [Problem(relative, 'python source', str(error))]
    return []


def _check_json(path: Path, relative: str) -> list:
    """The problems of one JSON file."""
    try:
        text = path.read_text('utf-8', errors='replace')
    except OSError:
        return []
    try:
        json.loads(text)
    except json.JSONDecodeError as error:
        return [Problem(relative, 'invalid JSON', error.msg, error.lineno)]
    except ValueError as error:
        return [Problem(relative, 'invalid JSON', str(error))]
    return []


def inspect_project(folder, *, max_files: int = MAX_FILES,
                    max_depth: int = MAX_DEPTH) -> Inspection:
    """Look at a project and say what is there and what is wrong with it."""
    root = Path(folder)
    result = Inspection(folder=str(root))
    if not root.is_dir():
        result.notes.append('That folder is not there any more.')
        return result
    protection = Protection(root)
    seen = 0
    for current, directories, files in os.walk(root):
        relative_dir = Path(current).relative_to(root)
        depth = 0 if relative_dir == Path('.') else len(relative_dir.parts)
        directories[:] = sorted(
            name for name in directories
            if name not in SKIP_DIRS
            and not (relative_dir / name).is_symlink()
            and depth < max_depth
            and not protection.blocked(str(relative_dir / name).replace('\\', '/')))
        if depth == 0:
            result.top_level = sorted(directories) + sorted(
                name for name in files if not protection.blocked(name))
        for name in sorted(files):
            if seen >= max_files:
                result.truncated = True
                break
            path = Path(current) / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = str(path.relative_to(root)).replace('\\', '/')
            if protection.blocked(relative):
                result.files_skipped += 1
                continue
            seen += 1
            result.files_inspected += 1
            try:
                size = path.stat().st_size
            except OSError:
                continue
            result.total_bytes += size
            kind = _kind_of(path)
            result.kinds[kind] = result.kinds.get(kind, 0) + 1
            if size > MAX_FILE_BYTES:
                continue
            suffix = path.suffix.casefold()
            if suffix == '.py':
                result.problems.extend(_check_python(path, relative))
            elif suffix == '.json':
                result.problems.extend(_check_json(path, relative))
            if len(result.problems) >= MAX_PROBLEMS:
                result.truncated = True
                break
        if seen >= max_files or result.truncated:
            break
    if result.truncated and result.notes == []:
        result.notes.append('Only part of the project was looked at.')
    return result
