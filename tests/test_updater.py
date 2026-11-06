import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from core import updater as u


def archive(files):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        for name, content in files.items():
            z.writestr(name, content)
    return data.getvalue()


class Updates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def release(self):
        return archive({'main.py': 'new main', 'ui.py': 'new ui',
                        'core/updater.py': 'new updater'})

    def stage(self):
        data = self.release()
        with patch.object(u, 'fetch', return_value=data):
            u.stage(self.root, {'available': True, 'version': '0.2.0',
                'url': 'https://example.test/release.zip', 'sha256': hashlib.sha256(data).hexdigest()})

    def test_install_restore_preserves_private_data(self):
        (self.root / 'main.py').write_text('old main')
        (self.root / 'config').mkdir()
        (self.root / 'config/api_keys.json').write_text('private')
        (self.root / 'memory').mkdir()
        (self.root / 'memory/facts.json').write_text('facts')
        self.stage()
        u.install(self.root)
        self.assertEqual(u.installed(self.root), '0.2.0')
        self.assertEqual((self.root / 'main.py').read_text(), 'new main')
        u.restore(self.root)
        self.assertEqual((self.root / 'main.py').read_text(), 'old main')
        self.assertFalse((self.root / 'ui.py').exists())
        self.assertEqual((self.root / 'config/api_keys.json').read_text(), 'private')
        self.assertEqual((self.root / 'memory/facts.json').read_text(), 'facts')
        self.assertEqual([r['action'] for r in u.history(self.root)], ['installed', 'restored'])

    def test_checksum_rejected(self):
        with patch.object(u, 'fetch', return_value=b'bad'):
            with self.assertRaisesRegex(ValueError, 'checksum'):
                u.stage(self.root, {'available': True, 'url': 'https://example.test/a', 'sha256': '0'*64})
        self.assertFalse((self.root / '.updates/pending.json').exists())

    def test_unsafe_and_private_paths_rejected(self):
        for name in ['../escape.py', '/absolute.py', 'core/../../escape.py',
                     'config/api_keys.json', 'memory/facts.json', 'core\\bad.py',
                     'core/file.py:stream', 'core/CON.py', 'core/file.py.']:
            with self.subTest(name=name):
                p = self.root / 'bad.zip'
                p.write_bytes(archive({name: 'bad'}))
                with self.assertRaises(ValueError):
                    u.unpack(p, self.root / 'extracted')

    def test_failed_copy_rolls_back(self):
        (self.root / 'main.py').write_text('old')
        self.stage()
        real = u.shutil.copy2
        failed = False
        def copy(src, dest):
            nonlocal failed
            if not failed and 'release-' in str(src) and Path(dest).name == 'ui.py':
                failed = True
                raise OSError('simulated disk failure')
            return real(src, dest)
        with patch.object(u.shutil, 'copy2', side_effect=copy):
            with self.assertRaises(OSError):
                u.install(self.root)
        self.assertEqual((self.root / 'main.py').read_text(), 'old')
        self.assertEqual(u.installed(self.root), u.VERSION)

    def test_manifest_validation_and_version_order(self):
        manifest = {'version': '0.10.0', 'url': 'https://example.test/a',
                    'sha256': 'a'*64, 'format': 'jarvis-blue-source-v1'}
        with patch.object(u, 'fetch', return_value=json.dumps(manifest).encode()):
            self.assertTrue(u.check('https://example.test/feed', '0.2.0')['available'])
        for url in ['http://example.test', 'https://user:secret@example.test']:
            with self.assertRaises(ValueError):
                u.https(url)

    def test_symlink_target_rejected(self):
        external = self.root / 'outside'
        external.mkdir()
        (self.root / 'core').symlink_to(external, target_is_directory=True)
        with self.assertRaises(ValueError):
            u.safe_target(self.root, 'core/updater.py')


if __name__ == '__main__':
    unittest.main()
