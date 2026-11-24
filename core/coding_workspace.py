"""The workspace boundary of the coding agent.

WHAT THIS IS
    A coding agent works inside one folder: the owner's project. This
    module is that folder, and everything that could reach outside it
    goes through here.

    It refuses:

    * a path that leaves the project, whether it is written as an
      absolute path or as a run of `..`;
    * a link that points out of the project;
    * a file the project keeps for itself — a secret by name, or
      anything its own `.gitignore` excludes. The rules live in
      `core.protection`, so the coding agent and the Codex task protect
      the same files.

    It writes atomically: a new file appears complete or not at all,
    and an edit that does not match exactly what was expected changes
    nothing.

WHAT THIS IS NOT
    * It is not a sandbox. It is a boundary that refuses the paths that
      would escape, and it is honest about what it does not check.
    * It does not run anything. The commands live in `core.coding_tools`
      and they are approved before they run.
"""
from __future__ import annotations

from dataclasses import dataclass
import difflib
import os
from pathlib import Path
import re
import tempfile

from core.protection import SKIP_DIRS, Protection

#: The largest file the agent reads in one go.
MAX_READ_CHARACTERS = 200_000

#: The largest file the agent writes.
MAX_WRITE_CHARACTERS = 200_000

#: How many search results one search returns.
MAX_SEARCH_RESULTS = 200

#: How many files one listing returns.
MAX_LIST_ENTRIES = 2000


class WorkspaceRefused(RuntimeError):
    """The path or the change was refused."""


@dataclass
class PatchResult:
    """What one patch did."""

    files: list
    applied: int = 0
    failed: list = None

    def __post_init__(self):
        if self.failed is None:
            self.failed = []

    def as_text(self) -> str:
        parts = [f'{self.applied} file(s) changed.']
        for name in self.files:
            parts.append(f'  {name}')
        for name, reason in self.failed:
            parts.append(f'  NOT applied: {name} — {reason}')
        return '\n'.join(parts)


def _normalise(path: str) -> str:
    return str(path or '').strip().replace('\\', '/')


class CodingWorkspace:
    """One project folder, and the only place the agent may write."""

    def __init__(self, root, *, extra_protected=()):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise WorkspaceRefused(f'The project folder {self.root} is not there.')
        self._protection = Protection(self.root)
        self._extra = tuple(_normalise(p) for p in extra_protected)

    # ------------------------------------------------------------------
    # the boundary

    def relative(self, path) -> str:
        """The path as the project sees it, with forward slashes."""
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            return candidate.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return candidate.as_posix()

    def resolve(self, path, *, must_exist=True) -> Path:
        """The real path of a file in the project, or a refusal."""
        name = _normalise(path)
        if not name:
            raise WorkspaceRefused('A file path is needed.')
        if '\x00' in name:
            raise WorkspaceRefused('That file path is not usable.')
        candidate = Path(name)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        if candidate.is_symlink():
            raise WorkspaceRefused('A link is not read or written here. Choose the real file.')
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(self.root)
        except ValueError:
            raise WorkspaceRefused(
                f'That path is outside the project. The agent only works in {self.root}.') from None
        if must_exist and not resolved.exists():
            raise WorkspaceRefused(f'{relative.as_posix()} is not in the project.')
        return resolved

    def is_protected(self, path) -> bool:
        """Whether the project keeps this file for itself.

        The rule is the one the Codex task already uses: a file that
        looks like a secret by name, or one the project's own
        `.gitignore` keeps out, is off limits.
        """
        try:
            relative = self.resolve(path, must_exist=False).relative_to(self.root).as_posix()
        except WorkspaceRefused:
            return False
        if relative in self._extra:
            return True
        return self._protection.blocked(relative)

    def _guard(self, path) -> tuple:
        """The resolved path and its project name, after the protection check."""
        resolved = self.resolve(path, must_exist=False)
        relative = resolved.relative_to(self.root).as_posix()
        if self.is_protected(relative):
            raise WorkspaceRefused(
                f'{relative} is protected: the project keeps it for itself, so the agent '
                'does not read or write it.')
        return resolved, relative

    # ------------------------------------------------------------------
    # reading

    def read_text(self, path) -> str:
        """The text of a file in the project."""
        resolved, relative = self._guard(path)
        if not resolved.is_file():
            raise WorkspaceRefused(f'{relative} is not a file in the project.')
        try:
            content = resolved.read_text('utf-8', errors='replace')
        except OSError as error:
            raise WorkspaceRefused(f'{relative} could not be read: {error}') from None
        if len(content) > MAX_READ_CHARACTERS:
            return content[:MAX_READ_CHARACTERS] + (
                f'\n\n[the file was cut short at {MAX_READ_CHARACTERS} characters]')
        return content

    def list_files(self, subpath='') -> list:
        """The files in the project, or in one folder of it."""
        start = self.resolve(subpath or '.', must_exist=False)
        try:
            start = start.resolve()
            start.relative_to(self.root)
        except ValueError:
            raise WorkspaceRefused('That folder is outside the project.') from None
        if not start.is_dir():
            raise WorkspaceRefused('That is not a folder in the project.')
        found = []
        for base, directories, files in os.walk(start):
            directories[:] = [name for name in directories
                              if name not in SKIP_DIRS and not name.startswith('.')]
            for name in sorted(files):
                if name.startswith('.'):
                    continue
                path = Path(base) / name
                try:
                    relative = path.relative_to(self.root).as_posix()
                except ValueError:
                    continue
                if self.is_protected(relative):
                    continue
                found.append(relative)
                if len(found) >= MAX_LIST_ENTRIES:
                    return found
        return found

    def search(self, pattern: str, subpath='', limit=MAX_SEARCH_RESULTS) -> list:
        """Find a text or a regular expression in the project."""
        if not pattern:
            raise WorkspaceRefused('Give something to search for.')
        try:
            expression = re.compile(pattern)
        except re.error as error:
            raise WorkspaceRefused(f'That search is not a valid pattern: {error}') from None
        results = []
        for relative in self.list_files(subpath):
            try:
                content = (self.root / relative).read_text('utf-8', errors='replace')
            except OSError:
                continue
            for number, line in enumerate(content.splitlines(), 1):
                if expression.search(line):
                    results.append({'file': relative, 'line': number, 'text': line.strip()[:300]})
                    if len(results) >= limit:
                        return results
        return results

    # ------------------------------------------------------------------
    # writing

    def write_text(self, path, content: str) -> str:
        """Write a file in the project, atomically."""
        if not isinstance(content, str):
            raise WorkspaceRefused('The content has to be text.')
        if len(content) > MAX_WRITE_CHARACTERS:
            raise WorkspaceRefused(f'That file is larger than {MAX_WRITE_CHARACTERS} characters.')
        resolved, relative = self._guard(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False,
                                            dir=str(resolved.parent),
                                            prefix='.jarvis-', suffix='.tmp')
        try:
            with handle as output:
                output.write(content)
            os.replace(handle.name, resolved)
        except OSError as error:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            raise WorkspaceRefused(f'{relative} could not be written: {error}') from None
        return relative

    def create_file(self, path, content: str) -> str:
        """Create a file that must not be there yet."""
        resolved, relative = self._guard(path)
        if resolved.exists():
            raise WorkspaceRefused(f'{relative} is already there.')
        return self.write_text(path, content)

    def edit_file(self, path, old: str, new: str, *, count: int = 1) -> str:
        """Replace exact text in a file.

        The text to replace has to be there, and it has to be there the
        number of times the caller said. An edit that would match more
        than one place is refused, because it would change something the
        caller did not mean to change.
        """
        if not isinstance(old, str) or not old:
            raise WorkspaceRefused('Give the text to replace.')
        if not isinstance(new, str):
            raise WorkspaceRefused('Give the text to put in its place.')
        relative = self.read_text(path)
        occurrences = relative.count(old)
        if occurrences == 0:
            raise WorkspaceRefused('That text is not in the file, so nothing was changed.')
        if count > 0 and occurrences != count:
            raise WorkspaceRefused(
                f'That text is in the file {occurrences} times, and {count} was expected, '
                'so nothing was changed.')
        updated = relative.replace(old, new, count if count > 0 else -1)
        return self.write_text(path, updated)

    # ------------------------------------------------------------------
    # patching

    def apply_patch(self, patch: str) -> PatchResult:
        """Apply a unified diff to the project.

        The diff is applied against the real text of the file. A hunk
        whose context does not match is refused and reported, so a patch
        that does not fit is never half-applied.
        """
        if not isinstance(patch, str) or not patch.strip():
            raise WorkspaceRefused('There is no patch to apply.')
        files = _split_patch(patch)
        if not files:
            raise WorkspaceRefused('No file was found in that patch.')
        result = PatchResult(files=[name for name, _ in files])
        for name, hunks in files:
            try:
                original = self.read_text(name)
            except WorkspaceRefused as error:
                result.failed.append((name, str(error)))
                continue
            updated, reason = _apply_hunks(original, hunks)
            if reason:
                result.failed.append((name, reason))
                continue
            try:
                self.write_text(name, updated)
            except WorkspaceRefused as error:
                result.failed.append((name, str(error)))
                continue
            result.applied += 1
        return result


def _split_patch(patch: str) -> list:
    """The files and hunks of a unified diff."""
    files = []
    current = None
    hunks = []
    lines = patch.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith('--- '):
            index += 1
            if index < len(lines) and lines[index].startswith('+++ '):
                target = lines[index][4:].strip()
                if target.startswith('b/'):
                    target = target[2:]
                current = target
                hunks = []
                index += 1
                continue
        elif line.startswith('@@'):
            header = line
            body = []
            index += 1
            while index < len(lines) and not lines[index].startswith(('@@', '--- ', 'diff ')):
                body.append(lines[index])
                index += 1
            if current is not None:
                hunks.append((header, body))
            continue
        index += 1
    if current is not None:
        files.append((current, hunks))
    return files


def _apply_hunks(original: str, hunks) -> tuple:
    """Apply the hunks to the text, or say why they did not fit."""
    result = original
    offset = 0
    for header, body in hunks:
        match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', header)
        if not match:
            return original, 'the hunk header could not be read'
        start = int(match.group(1)) - 1 + offset
        old_lines = []
        new_lines = []
        for line in body:
            if not line:
                continue
            marker, text = line[0], line[1:]
            if marker == ' ':
                old_lines.append(text)
                new_lines.append(text)
            elif marker == '-':
                old_lines.append(text)
            elif marker == '+':
                new_lines.append(text)
            elif marker == '\\':
                continue
            else:
                return original, 'the hunk has a line that is not a change'
        lines = result.splitlines()
        if start < 0 or start + len(old_lines) > len(lines):
            return original, 'the hunk does not fit in the file'
        if lines[start:start + len(old_lines)] != old_lines:
            # The file moved since the diff was made. The change is
            # refused rather than guessed at.
            return original, 'the context does not match the file'
        lines[start:start + len(old_lines)] = new_lines
        result = '\n'.join(lines)
        if original.endswith('\n') and not result.endswith('\n'):
            result += '\n'
        offset += len(new_lines) - len(old_lines)
    return result, None


def unified_diff(before: str, after: str, name: str) -> str:
    """A unified diff of two texts, for the owner to read."""
    return '\n'.join(difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=f'a/{name}', tofile=f'b/{name}', lineterm=''))


__all__ = ['CodingWorkspace', 'MAX_LIST_ENTRIES', 'MAX_READ_CHARACTERS',
           'MAX_SEARCH_RESULTS', 'MAX_WRITE_CHARACTERS', 'PatchResult',
           'WorkspaceRefused', 'unified_diff']
