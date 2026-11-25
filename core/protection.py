"""Local rules for keeping private workspace files out of coding requests."""
from collections.abc import Mapping
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re
import tomllib


SKIP_DIRS = frozenset((
    '.git', '.hg', '.svn', 'node_modules', 'env', 'venv', '.venv', '__pycache__',
    '.mypy_cache', '.pytest_cache', 'dist', 'build', '.idea', '.vscode', '.next',
    'target', '.jarvis_backup',
))
PRIVATE_EXTENSIONS = {'.pem', '.key', '.p12', '.pfx', '.keystore', '.jks'}
DATA_EXTENSIONS = {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
                   '.txt', '.env', '.properties', '.xml'}
PRIVATE_WORD = re.compile(r'credential|secret|passw(?:ord|d)|token|api[_-]?key', re.I)


def ignore_patterns(folder):
    ignore_file = Path(folder) / '.gitignore'
    try:
        lines = ignore_file.read_text(encoding='utf-8-sig').splitlines()
    except (OSError, UnicodeError):
        return []
    return [line.strip() for line in lines
            if line.strip() and not line.lstrip().startswith(('#', '!'))]


def is_ignored(relative, patterns):
    parts = relative.replace('\\', '/').split('/')
    for raw in patterns:
        directory_only = raw.endswith('/')
        rule = raw.strip('/')
        ancestors = len(parts) - int(directory_only)
        if '/' in rule or raw.startswith('/'):
            if any(fnmatchcase('/'.join(parts[:end]), rule) for end in range(1, ancestors + 1)):
                return True
        elif any(fnmatchcase(component, rule) for component in parts[:ancestors]):
            return True
    return False


def private_name(relative):
    path = Path(relative)
    name = path.name.lower()
    return (name == '.env' or name.startswith('.env.')
            or re.fullmatch(r'id_(rsa|dsa|ecdsa|ed25519)(\.pub)?', name) is not None
            or path.suffix.lower() in PRIVATE_EXTENSIONS
            or (path.suffix.lower() in DATA_EXTENSIONS and PRIVATE_WORD.search(name) is not None))


class Protection:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.patterns = ignore_patterns(self.folder)

    def reason(self, relative):
        relative = str(relative).replace('\\', '/').lstrip('/')
        if private_name(relative):
            return 'the name identifies a secret or credential file'
        if relative != '.gitignore' and is_ignored(relative, self.patterns):
            return 'the project excludes it in .gitignore'
        return ''

    def blocked(self, relative):
        return bool(self.reason(relative))

    def protected_files(self, limit=500):
        found = []
        for file in sorted(self.folder.rglob('*')):
            if len(found) == limit:
                break
            if file.is_symlink() or not file.is_file():
                continue
            relative = file.relative_to(self.folder)
            if not SKIP_DIRS.intersection(relative.parts) and self.blocked(relative.as_posix()):
                found.append(relative.as_posix())
        return found

    def notice(self):
        files = self.protected_files()
        if not files:
            return ''
        names = ', '.join(files[:12])
        return 'These files are off limits for reading and editing: ' + names + (' …' if len(files) > 12 else '')


def _config(text, extension):
    if extension == '.json':
        return json.loads(text)
    if extension == '.toml':
        return tomllib.loads(text)
    if extension in ('.yaml', '.yml'):
        import yaml
        return yaml.safe_load(text)
    return None


def _field_paths(value, prefix=()):
    if isinstance(value, Mapping):
        for key, nested in value.items():
            field = (*prefix, str(key))
            yield '.'.join(field)
            yield from _field_paths(nested, field)


def dropped_data(relative, old, new):
    extension = Path(relative).suffix.lower()
    try:
        before, after = _config(old, extension), _config(new, extension)
    except Exception:
        return ''
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return ''
    return ', '.join(sorted(set(_field_paths(before)) - set(_field_paths(after)))[:12])
