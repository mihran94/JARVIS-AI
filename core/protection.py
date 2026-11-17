"""Which files of a project a coding agent may not read, and may not change.

WHERE THIS COMES FROM
    The Mark LVI source, `core/code_checks.py`, worked out the same thing for
    its own coding agent and wrote down why:

        "Learned from a real job: asked to add a plugin, the model also
        'edited' config/api_keys.json to switch the plugin on — rewrote the
        whole file from memory, dropped the API keys and half the settings,
        and the app asked for its key again on the next start. Worse, that
        file had been read into the project context, so the keys in it went
        to the model with every request."

    Two kinds of file are out of reach, and the decision is made here rather
    than left to a prompt:

    * anything that looks like a secret by name;
    * anything the project's own `.gitignore` excludes, because that is
      exactly what a repository keeps out — local settings, personal data,
      logs and build output.

    The names that mean "secret" only apply to DATA files. Source code
    called `api_keys.py` is code a project may well need changed, so only
    `.json`, `.yaml`, `.toml` and friends are matched by those names.

WHAT THIS DOES FOR JARVIS
    * The project context sent to a provider leaves out every protected file,
      so a key never travels to MiniMax.
    * A proposed change may not write a protected file.
    * The Codex task is told which files are off limits, and the result says
      so when a protected file would have been touched.
    * An edit that silently drops keys from a settings file is reported
      instead of being applied quietly.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from fnmatch import fnmatch

#: The names that mean "this file holds secrets".
_SECRET_RE = re.compile(
    r"(^|/)(\.env(\..*)?|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|.*\.(pem|key|p12|pfx|keystore|jks)|"
    r".*(secret|credential|password|passwd|token|api[_-]?keys?).*"
    r"\.(json|ya?ml|toml|ini|cfg|conf|txt|env|properties|xml))$",
    re.IGNORECASE)

#: The folders that are never part of a project's source.
SKIP_DIRS = frozenset({'.git', '.hg', '.svn', 'node_modules', 'venv', '.venv', 'env',
                       '__pycache__', '.mypy_cache', '.pytest_cache', 'dist', 'build',
                       '.idea', '.vscode', '.next', 'target', '.jarvis_backup'})


def ignore_patterns(folder) -> list[str]:
    """The patterns in the project's own `.gitignore`.

    Negations are ignored on purpose: keeping more out protects more, and a
    negation can only widen what is read.
    """
    try:
        lines = (Path(folder) / '.gitignore').read_text('utf-8', errors='replace').splitlines()
    except OSError:
        return []
    patterns = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('!'):
            continue
        line = re.split(r'\s+#', line, maxsplit=1)[0].strip()
        if line:
            patterns.append(line)
    return patterns


def is_ignored(relative: str, patterns: list[str]) -> bool:
    """True when the project's `.gitignore` keeps this path out."""
    parts = relative.split('/')
    for pattern in patterns:
        is_dir = pattern.endswith('/')
        pattern = pattern.strip('/')
        anchored = '/' in pattern
        pattern = pattern.replace('**/', '')
        if anchored:
            for index in range(1, len(parts) + 1):
                prefix = '/'.join(parts[:index])
                if fnmatch(prefix, pattern) and (not is_dir or index < len(parts)):
                    return True
        else:
            for index, segment in enumerate(parts):
                if fnmatch(segment, pattern) and (not is_dir or index < len(parts) - 1):
                    return True
    return False


class Protection:
    """Which files of one project are off limits, and why."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.patterns = ignore_patterns(self.folder)

    def reason(self, relative: str) -> str:
        """Why this file may not be read or changed, or '' when it may."""
        relative = str(relative).replace('\\', '/').lstrip('/')
        if _SECRET_RE.search(relative):
            return 'it looks like a file of secrets (keys, tokens, passwords)'
        if relative != '.gitignore' and is_ignored(relative, self.patterns):
            return ('the project\'s .gitignore keeps it out of the code '
                    '(local settings, data or output)')
        return ''

    def blocked(self, relative: str) -> bool:
        """True when this file is off limits."""
        return bool(self.reason(relative))

    def protected_files(self, limit: int = 500) -> list[str]:
        """The protected files that are actually in the project."""
        found = []
        if not self.folder.is_dir():
            return found
        for path in sorted(self.folder.rglob('*')):
            if len(found) >= limit:
                break
            if not path.is_file() or path.is_symlink():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            relative = str(path.relative_to(self.folder)).replace('\\', '/')
            if self.blocked(relative):
                found.append(relative)
        return found

    def notice(self) -> str:
        """A sentence for the prompt, naming what is off limits."""
        files = self.protected_files()
        if not files:
            return ''
        listed = ', '.join(files[:12]) + (' …' if len(files) > 12 else '')
        return (f'These files of this project are off limits. Do not read them, do not '
                f'change them and do not ask for their contents: {listed}. '
                'They hold secrets or local data that the project keeps out of its code.')


def dropped_data(relative: str, old: str, new: str) -> str:
    """What an edit of a settings file throws away, or ''.

    A model that "adds one setting" to a JSON file writes the whole file again
    from what it remembers, and anything it did not remember is gone. Removing
    a key is rarely what was asked, and never something to do silently.
    """
    extension = Path(relative).suffix.lower()

    def keys(text):
        if extension == '.json':
            data = json.loads(text)
        elif extension == '.toml':
            import tomllib
            data = tomllib.loads(text)
        elif extension in ('.yml', '.yaml'):
            try:
                import yaml
            except ImportError:
                return None
            data = yaml.safe_load(text)
        else:
            return None
        if not isinstance(data, dict):
            return None
        found = set()
        for key, value in data.items():
            found.add(str(key))
            if isinstance(value, dict):
                found.update(f'{key}.{inner}' for inner in value)
        return found

    try:
        before, after = keys(old), keys(new)
    except Exception:
        return ''
    if before is None or after is None:
        return ''
    lost = sorted(before - after)
    return ', '.join(lost[:12]) if lost else ''
