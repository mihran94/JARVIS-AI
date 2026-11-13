"""Source-release updates. No package installs, builds, or credentials in backups."""
from __future__ import annotations
import hashlib
import json
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

VERSION = '0.1.0'
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024
# Only application-owned source/assets. Runtime data is deliberately excluded.
ROOT_FILES = {'main.py', 'ui.py', 'setup.py', 'requirements.txt', 'README.md', 'readme.md',
              'LICENSE', 'AGENTS.md', 'UPDATE_PLAN.md', 'UPDATE_GUIDE.md',
              'SIGNING_GUIDE.md', 'DEVELOPMENT_BLUEPRINT.md', 'launcher.py',
              'SETUP_JARVIS.cmd', 'START_JARVIS.cmd'}
CODE_DIRS = {'core', 'actions', 'providers', 'plugins', 'dashboard'}

def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Release versions must use major.minor.patch.')
    return tuple(map(int, value.split('.')))

def https(url):
    from urllib.parse import urlsplit
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password:
        raise ValueError('An HTTPS release URL without embedded credentials is required.')
    return url

def fetch(url, limit):
    with urllib.request.urlopen(https(url), timeout=20) as response:
        https(response.geturl())
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Release download exceeds size limit.')
    return data

def check(url, current=VERSION):
    manifest = json.loads(fetch(url, 256 * 1024))
    from core.release_security import verify
    verify(manifest)
    version(manifest['version'])
    https(manifest['url'])
    if not re.fullmatch(r'[a-fA-F0-9]{64}', manifest.get('sha256', '')):
        raise ValueError('Release SHA-256 is missing or invalid.')
    if manifest.get('format') != 'jarvis-blue-source-v1':
        raise ValueError('Unsupported release format.')
    manifest['available'] = version(manifest['version']) > version(current)
    manifest['notes'] = manifest['notes']
    return manifest

def managed(name):
    p = PurePosixPath(name)
    if '\\' in name or p.is_absolute() or '..' in p.parts or not p.parts:
        return False
    if any(part.startswith('.') or part == '__pycache__' or ':' in part or
           part.endswith((' ', '.')) or part.split('.')[0].upper() in
           {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
            *(f'LPT{i}' for i in range(1, 10))} for part in p.parts):
        return False
    if len(p.parts) == 1:
        return name in ROOT_FILES
    if p.parts[0] == 'memory':
        return len(p.parts) == 2 and p.suffix == '.py'
    if p.parts[0] == 'config':
        return name in {'config/__init__.py', 'config/jarvis.ico'}
    if name in {'core/update_trust.json', 'tools/setup_environment.py'}:
        return True
    if p.parts[0] not in CODE_DIRS:
        return False
    return p.suffix.lower() in {'.py', '.html', '.js', '.css', '.obj', '.txt', '.svg', '.png', '.ico'}

def unpack(archive, target):
    seen = set()
    total = 0
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist()) > 5000:
            raise ValueError('Too many release files.')
        for item in z.infolist():
            if item.is_dir():
                continue
            name = item.filename
            if not managed(name) or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError(f'Unsupported release path: {name}')
            if name.casefold() in seen:
                raise ValueError('Duplicate release path.')
            seen.add(name.casefold())
            total += item.file_size
            if total > MAX_EXPANDED:
                raise ValueError('Expanded release exceeds size limit.')
            dest = target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(item) as src, dest.open('wb') as out:
                shutil.copyfileobj(src, out)
    if not {'main.py', 'ui.py', 'core/updater.py'} <= seen:
        raise ValueError('Release is missing required application files.')

def stage(root, manifest):
    from core.release_security import verify
    verify(manifest)
    version(manifest['version'])
    https(manifest['url'])
    if not re.fullmatch(r'[a-fA-F0-9]{64}', manifest['sha256']):
        raise ValueError('Invalid release checksum.')
    if manifest.get('format') != 'jarvis-blue-source-v1':
        raise ValueError('Unsupported release format.')
    if version(manifest['version']) <= version(installed(root)):
        raise ValueError('No newer release selected.')
    state = root / '.updates'
    state.mkdir(exist_ok=True)
    archive = state / 'download.part'
    archive.write_bytes(fetch(manifest['url'], MAX_ARCHIVE))
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['sha256'].lower():
        archive.unlink(missing_ok=True)
        raise ValueError('Release checksum mismatch; update rejected.')
    staged = Path(tempfile.mkdtemp(prefix='release-', dir=state))
    try:
        unpack(archive, staged)
        archive.replace(staged / 'verified.zip')
        atomic_json(state / 'pending.json', {'directory': staged.name,
            'version': manifest['version'], 'manifest': manifest})
    except Exception:
        shutil.rmtree(staged)
        raise
    finally:
        archive.unlink(missing_ok=True)
    return 'Download verified. Ready to install and restart.'

def history(root):
    path = root / '.updates/history.json'
    return json.loads(path.read_text()) if path.exists() else []

def record(root, event):
    rows = history(root)
    rows.append(dict(event, time=time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())))
    atomic_json(root / '.updates/history.json', rows[-100:])

def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    tmp.replace(path)

def safe_target(root, name):
    if not managed(name):
        raise ValueError('Unmanaged target.')
    p = root / name
    # Do not follow user-created symlinks outside the application tree.
    if any(q.is_symlink() for q in [p, *p.parents] if q != root.parent):
        raise ValueError('Symlink target rejected.')
    if not p.resolve().is_relative_to(root.resolve()):
        raise ValueError('Target escapes application directory.')
    return p

def restore(root):
    state = root / '.updates'
    info_path = state / 'backup.json'
    if not info_path.exists():
        raise ValueError('No previous update backup exists.')
    info = json.loads(info_path.read_text())
    for name, existed in info['files'].items():
        dest = safe_target(root, name)
        if existed:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(state / 'backup' / name, dest)
        else:
            dest.unlink(missing_ok=True)
    atomic_json(state / 'installed.json', {'version': info['version']})
    (state / 'pending.json').unlink(missing_ok=True)
    record(root, {'action': 'restored', 'version': info['version']})
    info_path.unlink()  # A backup is consumed; do not offer it as another version.

def installed(root):
    path = root / '.updates/installed.json'
    return json.loads(path.read_text())['version'] if path.exists() else VERSION

def install(root):
    state = root / '.updates'
    pending = json.loads((state / 'pending.json').read_text())
    directory = pending['directory']
    if not re.fullmatch(r'release-[a-zA-Z0-9_]+', directory):
        raise ValueError('Invalid staged release.')
    staged = state / directory
    if state.is_symlink() or staged.is_symlink():
        raise ValueError('Symlink update directory rejected.')
    from core.release_security import verify
    manifest = pending['manifest']
    verify(manifest)
    if manifest['version'] != pending['version'] or version(manifest['version']) <= version(installed(root)):
        raise ValueError('Stale or inconsistent pending update.')
    archive = staged / 'verified.zip'
    if archive.is_symlink() or hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['sha256'].lower():
        raise ValueError('Staged release checksum mismatch.')
    # Re-extract the signed archive at install time; never execute loose staged edits.
    payload = staged / 'payload'
    if payload.exists():
        shutil.rmtree(payload)
    payload.mkdir()
    unpack(archive, payload)
    staged_source = payload
    files = [p for p in staged_source.rglob('*') if p.is_file()]
    if not files or any(p.is_symlink() for p in staged.rglob('*')):
        raise ValueError('Invalid staged files.')
    names = [p.relative_to(staged_source).as_posix() for p in files]
    for name in names:
        safe_target(root, name)
    # Keep previous backup until a complete replacement backup is ready.
    tmp = Path(tempfile.mkdtemp(prefix='backup-', dir=state))
    info = {'version': installed(root), 'files': {}}
    try:
        for name in names:
            source = root / name
            info['files'][name] = source.exists()
            if source.exists():
                dest = tmp / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
        shutil.rmtree(state / 'backup', ignore_errors=True)
        tmp.rename(state / 'backup')
        atomic_json(state / 'backup.json', info)
        try:
            for name in names:
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged_source / name, dest)
            atomic_json(state / 'installed.json', {'version': pending['version']})
            record(root, {'action': 'installed', 'version': pending['version']})
            (state / 'pending.json').unlink()
        except Exception:
            restore(root)
            raise
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    shutil.rmtree(staged)

def launch_helper(root, rollback=False):
    if getattr(sys, 'frozen', False):
        raise ValueError('Packaged-app updating requires a future installer release.')
    import os
    state = root / '.updates'
    state.mkdir(exist_ok=True)
    helper = state / 'update_runner.py'
    shutil.copy2(Path(__file__), helper)
    log = (state / 'updater.log').open('a', encoding='utf-8')
    try:
        subprocess.Popen([sys.executable, str(helper), str(root), str(os.getpid()),
                          'restore' if rollback else 'install'], cwd=root,
                         stdout=log, stderr=log)
    finally:
        log.close()

def wait_for_parent(pid):
    import os
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if handle:
            try:
                if kernel.WaitForSingleObject(handle, 120000) != 0:
                    raise RuntimeError('App did not exit; update cancelled.')
            finally:
                kernel.CloseHandle(handle)
        elif ctypes.get_last_error() != 87:
            raise RuntimeError('Could not verify app exit; update cancelled.')
    else:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.25)
        raise RuntimeError('App did not exit; update cancelled.')

if __name__ == '__main__':
    app_root = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(app_root))
    try:
        wait_for_parent(int(sys.argv[2]))
        (restore if sys.argv[3] == 'restore' else install)(app_root)
        subprocess.Popen([sys.executable, str(app_root / 'main.py')], cwd=app_root)
    except Exception as error:
        print(f'Update failed: {error}', flush=True)
        sys.exit(1)
