import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from core import updater as u
from core import release_security as security
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools.sign_update import sign
import base64


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
        self.key = Ed25519PrivateKey.generate()
        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.keys = {hashlib.sha256(raw).hexdigest()[:24]: base64.b64encode(raw).decode()}
        patcher = patch.object(security, 'trusted_keys', return_value=self.keys)
        patcher.start()
        self.addCleanup(patcher.stop)
        signer = patch('tools.sign_update.trusted_keys', return_value=self.keys)
        signer.start()
        self.addCleanup(signer.stop)

    def manifest(self, data=None, **changes):
        manifest = {'version': '0.2.0', 'url': 'https://example.test/release.zip',
            'sha256': hashlib.sha256(data or self.release()).hexdigest(),
            'format': 'jarvis-blue-source-v1', 'notes': 'Test release'}
        manifest.update(changes)
        return sign(manifest, self.key)

    def release(self):
        return archive({'main.py': 'new main', 'ui.py': 'new ui',
                        'core/updater.py': 'new updater'})

    def stage(self):
        data = self.release()
        with patch.object(u, 'fetch', return_value=data):
            u.stage(self.root, self.manifest(data))

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
                u.stage(self.root, self.manifest(sha256='0'*64))
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
        manifest = self.manifest(version='0.10.0', sha256='a'*64)
        with patch.object(u, 'fetch', return_value=json.dumps(manifest).encode()):
            self.assertTrue(u.check('https://example.test/feed', '0.2.0')['available'])
        for url in ['http://example.test', 'https://user:secret@example.test']:
            with self.assertRaises(ValueError):
                u.https(url)

    def test_unsigned_and_modified_manifest_rejected(self):
        for field in ['version', 'url', 'sha256', 'notes', 'expires', 'key_id', 'format']:
            with self.subTest(field=field):
                manifest = self.manifest()
                manifest[field] += 'changed'
                with self.assertRaises(ValueError):
                    security.verify(manifest)
        manifest = self.manifest()
        del manifest['signature']
        with self.assertRaises(ValueError):
            security.verify(manifest)

    def test_unknown_key_and_unconfigured_trust_rejected(self):
        manifest = self.manifest()
        for keys in [{}, {'another-key': next(iter(self.keys.values()))}]:
            with patch.object(security, 'trusted_keys', return_value=keys):
                with self.assertRaises(ValueError):
                    security.verify(manifest)

    def test_expired_signed_manifest_rejected(self):
        manifest = self.manifest()
        manifest['expires'] = '2020-01-01T00:00:00Z'
        manifest['signature'] = base64.b64encode(self.key.sign(security.canonical(manifest))).decode()
        with self.assertRaisesRegex(ValueError, 'expired'):
            security.verify(manifest)

    def test_downgrade_rejected_even_when_signed(self):
        with self.assertRaisesRegex(ValueError, 'newer'):
            u.stage(self.root, self.manifest(version='0.0.1'))

    def test_staged_archive_tampering_rejected(self):
        self.stage()
        pending = json.loads((self.root / '.updates/pending.json').read_text())
        (self.root / '.updates' / pending['directory'] / 'verified.zip').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            u.install(self.root)
        self.assertFalse((self.root / 'main.py').exists())

    def test_pending_manifest_tampering_rejected(self):
        self.stage()
        path = self.root / '.updates/pending.json'
        pending = json.loads(path.read_text())
        pending['manifest']['version'] = '9.9.9'
        path.write_text(json.dumps(pending))
        with self.assertRaisesRegex(ValueError, 'signature'):
            u.install(self.root)

    def test_loose_staging_changes_not_installed(self):
        self.stage()
        pending = json.loads((self.root / '.updates/pending.json').read_text())
        (self.root / '.updates' / pending['directory'] / 'main.py').write_text('tampered loose file')
        u.install(self.root)
        self.assertEqual((self.root / 'main.py').read_text(), 'new main')

    def test_symlink_target_rejected(self):
        external = self.root / 'outside'
        external.mkdir()
        (self.root / 'core').symlink_to(external, target_is_directory=True)
        with self.assertRaises(ValueError):
            u.safe_target(self.root, 'core/updater.py')


if __name__ == '__main__':
    unittest.main()
