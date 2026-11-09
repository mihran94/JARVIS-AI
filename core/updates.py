"""Owner-approved source ZIP staging; no download, dependency install or code execution."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

MAX_ARCHIVE = 50_000_000
MAX_EXPANDED = 100_000_000
REQUIRED = {'main.py', 'requirements.txt', 'desktop/app.py', 'core/store.py'}


class UpdateError(ValueError):
    pass


def installation_root():
    return Path(os.environ.get('JARVIS_INSTALL_ROOT', Path(__file__).resolve().parents[1])).resolve()


def read_state(root):
    path = Path(root) / '.updates' / 'state.json'
    if not path.exists():
        return {'active': 'base', 'previous': None}
    try:
        state = json.loads(path.read_text('utf-8'))
        release_path(root, state['active'])
        if state.get('previous') is not None:
            release_path(root, state['previous'])
        return state
    except (OSError, ValueError, KeyError, TypeError):
        raise UpdateError('Update state is invalid. Use the original main.py to recover.') from None


def release_path(root, ident):
    root = Path(root).resolve()
    if ident == 'base':
        return root
    if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{64}', ident):
        raise UpdateError('Invalid release identifier.')
    path = root / '.updates' / 'releases' / ident
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise UpdateError('Release path leaves the installation.')
    return path


def inspect_zip(path):
    path = Path(path)
    if path.stat().st_size > MAX_ARCHIVE:
        raise UpdateError('Update ZIP exceeds 50 MB.')
    data = path.read_bytes()
    if len(data) > MAX_ARCHIVE:
        raise UpdateError('Update ZIP exceeds 50 MB.')
    import io
    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 3000:
            raise UpdateError('Too many ZIP entries.')
        roots = {item.filename.split('/')[0] for item in entries}
        if len(roots) != 1:
            raise UpdateError('Choose a GitHub source ZIP with one top-level folder.')
        total = 0
        seen = set()
        for item in entries:
            name = item.filename
            parts = name.rstrip('/').split('/')
            if ('\\' in name or name.startswith('/') or any(
                    p in ('', '.', '..') or p.endswith((' ', '.')) or ':' in p
                    or any(ord(c) < 32 or c in '<>"|?*' for c in p)
                    or p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',
                        *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}
                    for p in parts)):
                raise UpdateError('Unsafe path in ZIP.')
            if stat.S_ISLNK(item.external_attr >> 16):
                raise UpdateError('Links are not permitted in an update.')
            if item.is_dir():
                continue
            if len(parts) < 2:
                raise UpdateError('Missing top-level source folder.')
            relative = '/'.join(parts[1:])
            if parts[1].lower() in {'.updates','.venv','.git'} or parts[1].lower().startswith('.env'):
                raise UpdateError('ZIP includes runtime data or credentials.')
            if relative.casefold() in seen:
                raise UpdateError('Duplicate or case-colliding path in ZIP.')
            seen.add(relative.casefold())
            total += item.file_size
            if item.file_size > 5_000_000 or total > MAX_EXPANDED:
                raise UpdateError('Expanded ZIP exceeds safety limits.')
            files[relative] = archive.read(item)
    if not REQUIRED <= files.keys():
        raise UpdateError('ZIP is missing required JARVIS source files.')
    return hashlib.sha256(data).hexdigest(), files


def changed_files(current, files):
    changes = []
    for name, content in sorted(files.items()):
        old = Path(current) / PurePosixPath(name)
        if not old.is_file() or old.read_bytes() != content:
            changes.append(name)
    return changes


def _write_state(root, state):
    folder = Path(root) / '.updates'
    if folder.is_symlink() or not folder.resolve().is_relative_to(Path(root).resolve()):
        raise UpdateError('Unsafe update directory.')
    folder.mkdir(exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='state-', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(state, out)
            out.flush(); os.fsync(out.fileno())
        os.replace(tmp, folder / 'state.json')
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def activate_zip(root, archive, expected_digest):
    root = Path(root).resolve()
    digest, files = inspect_zip(archive)
    if digest != expected_digest:
        raise UpdateError('ZIP changed after review; review it again.')
    if files['requirements.txt'].strip() != (root / 'requirements.txt').read_bytes().strip():
        raise UpdateError('Dependencies changed. Install this release separately with setup.cmd.')
    if files['core/store.py'] != (root / 'core/store.py').read_bytes():
        raise UpdateError('Database code changed. Use a separate installation for this release.')
    state = read_state(root)
    if state['active'] == digest:
        raise UpdateError('This release is already selected.')
    target = release_path(root, digest)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.parent.resolve().is_relative_to(root):
        raise UpdateError('Unsafe release directory.')
    if target.exists():
        if any(p.is_symlink() for p in target.rglob('*')):
            raise UpdateError('Stored release contains a link.')
        # Refuse replacing a previous release; its contents must still match the archive.
        existing = {str(p.relative_to(target)).replace(os.sep, '/'): p.read_bytes()
                    for p in target.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        if existing != files:
            raise UpdateError('Stored release differs from the reviewed ZIP.')
    else:
        staging = Path(tempfile.mkdtemp(prefix='stage-', dir=target.parent))
        try:
            for name, content in files.items():
                out = staging / PurePosixPath(name)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(content)
            os.replace(staging, target)
        finally:
            if staging.exists(): shutil.rmtree(staging)
    _write_state(root, {'active': digest, 'previous': state['active']})
    return 'Update staged. Close JARVIS and use START_JARVIS.cmd. Previous code is retained.'


def rollback(root):
    state = read_state(root)
    previous = state.get('previous')
    if previous is None or not (release_path(root, previous) / 'main.py').is_file():
        raise UpdateError('No retained previous release is available.')
    _write_state(root, {'active': previous, 'previous': state['active']})
    return 'Previous code selected for next startup. User data was not restored or changed.'
