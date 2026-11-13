"""Read-only, local project inspection. Never imports or executes project code."""
from pathlib import Path
import os
import re

EXCLUDED = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.ssh',
            'api_keys.json', 'credentials.json', 'secrets.json'}
TEXT_SUFFIXES = {'.py', '.md', '.txt', '.json', '.toml', '.yaml', '.yml',
                 '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.ini', '.cfg',
                 '.cmd', '.bat', '.ps1', '.sh', '.csv', '.gitignore'}
MAX_BYTES = 128 * 1024
MAX_ENTRIES = 500


def _hidden(name):
    lower = name.lower()
    return lower in EXCLUDED or lower.startswith('.env') or lower.endswith(('.pem', '.key', '.p12', '.pfx'))


class ProjectWorkspace:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('Choose a project folder.')

    def _path(self, relative):
        relative = Path(relative)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Path must stay inside the selected project.')
        path = self.root
        for part in relative.parts:
            if _hidden(part):
                raise ValueError('Environment, credential or generated files are excluded.')
            path = path / part
            if path.is_symlink():
                raise ValueError('Symbolic links are excluded.')
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(self.root):
            raise ValueError('Path leaves the selected project.')
        return resolved

    def list_directory(self, relative='.'):
        path = self._path(relative)
        entries = []
        truncated = False
        with os.scandir(path) as listing:
            for entry in listing:
                if _hidden(entry.name) or entry.is_symlink():
                    continue
                if len(entries) == MAX_ENTRIES:
                    truncated = True
                    break
                entries.append((entry.name, entry.is_dir(follow_symlinks=False)))
        return sorted(entries, key=lambda item: (not item[1], item[0].lower())), truncated

    def read_text(self, relative):
        path = self._path(relative)
        if not path.is_file():
            raise ValueError('Select a regular text file.')
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {'LICENSE', '.gitignore', 'Dockerfile', 'Makefile'}:
            raise ValueError('Preview supports source and text files only.')
        with path.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('File exceeds the 128 KiB preview limit.')
        if b'\0' in data:
            raise ValueError('Binary files cannot be previewed.')
        try:
            return data.decode('utf-8-sig')
        except UnicodeDecodeError as error:
            raise ValueError('Preview requires UTF-8 text.') from error


def diagnose_traceback(text):
    """Rule-based guidance; pasted logs are data, never commands."""
    if len(text) > MAX_BYTES:
        return 'Error text exceeds 128 KiB. Paste only the final traceback.'
    matches = re.findall(r'^\s*([A-Za-z_][\w.]*(?:Error|Exception))\s*:\s*(.*)$', text, re.MULTILINE)
    if not matches:
        return 'No recognized Python exception found. Paste the complete traceback, including its final error line.'
    name, detail = matches[-1]
    short = name.rsplit('.', 1)[-1]
    guidance = {
        'ModuleNotFoundError': 'Check which Python interpreter and virtual environment launched the app. Compare the missing module with requirements.txt before installing anything; import names can differ from package names.',
        'ImportError': 'Check the installed dependency version and look for a local file shadowing the imported package or a circular import.',
        'FileNotFoundError': 'Check the named file, working directory and configured path. Use a path relative to the project location where appropriate.',
        'PermissionError': 'Check access to the selected file and whether another program has locked it. Choose an accessible project folder.',
        'SyntaxError': 'Inspect the reported line and the preceding line for missing brackets, quotes or colons. Check the supported Python version.',
        'IndentationError': 'Inspect the reported block. Use consistent spaces and align it with the surrounding Python block.',
        'TabError': 'Replace mixed tabs and spaces with consistent indentation in the reported block.',
        'NameError': 'Check spelling and whether the name is defined or imported before this line runs.',
        'AttributeError': 'Check the actual object type and whether this attribute exists in the installed library version.',
        'TypeError': 'Compare the supplied arguments and value types with the called function.',
        'ValueError': 'Check the input value and expected format at the failing line.',
        'ConnectionError': 'Check the configured endpoint and connection. Do not paste credentials into shared logs.',
        'TimeoutError': 'Check service availability and configured deadlines before retrying.',
    }.get(short, 'Inspect the final traceback frame and the input that caused this exception. This error needs project-specific investigation.')
    return f'{name}: {detail}\n\nSuggested checks\n{guidance}\n\nLocal rule-based guidance only. No code was run or changed; this is not a verified fix.'
