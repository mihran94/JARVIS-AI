"""Create source-update ZIP + manifest when explicitly preparing a release.
Usage: python tools/prepare_source_release.py 0.2.0 https://host/Jarvis-Blue-0.2.0.zip
This does not publish, install dependencies or build an executable.
"""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.updater import managed, version, https


def main():
    release_version, download_url = sys.argv[1:]
    version(release_version)
    https(download_url)
    out = ROOT / 'release-output'
    out.mkdir(exist_ok=True)
    archive = out / f'Jarvis-Blue-{release_version}.zip'
    # Explicit managed roots, never traverse user data, environment or backups.
    candidates = [ROOT / name for name in ('main.py', 'ui.py', 'setup.py',
        'requirements.txt', 'README.md', 'readme.md', 'LICENSE', 'AGENTS.md', 'UPDATE_PLAN.md', 'UPDATE_GUIDE.md')]
    for directory in ('core', 'actions', 'providers', 'plugins', 'dashboard', 'memory', 'config'):
        candidates.extend((ROOT / directory).rglob('*'))
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(candidates):
            if path.is_file() and not path.is_symlink() and managed(path.relative_to(ROOT).as_posix()):
                z.write(path, path.relative_to(ROOT))
    manifest = {'format': 'jarvis-blue-source-v1', 'version': release_version,
                'url': download_url, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                'notes': 'Describe this release before publishing.'}
    (out / 'latest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Unsigned source archive and latest.json prepared. Edit notes, then run tools/sign_update.py before publishing.')

if __name__ == '__main__':
    main()
