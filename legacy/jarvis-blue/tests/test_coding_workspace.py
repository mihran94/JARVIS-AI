import tempfile
from pathlib import Path
import unittest
from core.coding_workspace import ProjectWorkspace, diagnose_traceback, MAX_BYTES, MAX_ENTRIES


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = ProjectWorkspace(self.root)

    def test_preview_and_directory_navigation(self):
        (self.root / 'src').mkdir()
        (self.root / 'src/main.py').write_text('print("hello")', encoding='utf-8')
        self.assertEqual(self.project.list_directory()[0], [('src', True)])
        self.assertEqual(self.project.read_text('src/main.py'), 'print("hello")')

    def test_scope_and_links(self):
        for name in ['../escape.py', str(self.root / 'absolute.py')]:
            with self.assertRaises(ValueError):
                self.project.read_text(name)
        target = self.root / 'real.py'
        target.write_text('secret')
        try:
            (self.root / 'link.py').symlink_to(target)
        except OSError:
            self.skipTest('Symlinks unavailable')
        with self.assertRaises(ValueError):
            self.project.read_text('link.py')
        self.assertNotIn(('link.py', False), self.project.list_directory()[0])

    def test_excluded_files_and_directories(self):
        for name in ['.env', '.env.local', 'api_keys.json', 'private.pem']:
            (self.root / name).write_text('secret')
            with self.assertRaises(ValueError):
                self.project.read_text(name)
        (self.root / '.venv').mkdir()
        self.assertEqual(self.project.list_directory(), ([], False))

    def test_preview_limits_and_encoding(self):
        file = self.root / 'data.txt'
        for data in [b'a' * (MAX_BYTES + 1), b'abc\0def', b'\xff']:
            file.write_bytes(data)
            with self.assertRaises(ValueError):
                self.project.read_text('data.txt')
        file.write_bytes(b'\xef\xbb\xbfhello')
        self.assertEqual(self.project.read_text('data.txt'), 'hello')

    def test_binary_extension_and_missing_file(self):
        (self.root / 'app.exe').write_text('text')
        with self.assertRaises(ValueError):
            self.project.read_text('app.exe')
        with self.assertRaises(FileNotFoundError):
            self.project.read_text('missing.py')

    def test_directory_limit_is_explicit(self):
        for index in range(MAX_ENTRIES + 1):
            (self.root / f'{index}.py').touch()
        entries, truncated = self.project.list_directory()
        self.assertEqual(len(entries), MAX_ENTRIES)
        self.assertTrue(truncated)

    def test_last_exception_and_missing_module_guidance(self):
        result = diagnose_traceback('ValueError: first\n\nModuleNotFoundError: No module named xyz')
        self.assertTrue(result.startswith('ModuleNotFoundError:'))
        self.assertIn('virtual environment', result)
        self.assertIn('not a verified fix', result)

    def test_unknown_and_oversized_input(self):
        self.assertIn('No recognized', diagnose_traceback('hello'))
        self.assertIn('project-specific', diagnose_traceback('CustomError: failed'))
        self.assertIn('exceeds', diagnose_traceback('x' * (MAX_BYTES + 1)))
