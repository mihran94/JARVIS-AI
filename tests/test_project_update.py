import tempfile, zipfile, unittest
from pathlib import Path
from core.project_update import UpdateSession

class UpdateTests(unittest.TestCase):
    def test_roundtrip_backup_conflict_and_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'input.zip'
            with zipfile.ZipFile(source,'w') as z:
                z.writestr('main.py','x = 1\n'); z.writestr('.env','secret')
            s=UpdateSession(source,root)
            self.assertEqual(len(s.skipped),1)
            p=s.preview('main.py','x = 2\n'); self.assertIn('+x = 2',p[3])
            s.apply(p); self.assertIn('1 Python',s.check())
            with self.assertRaises(ValueError): s.apply(p)
            s.export(root/'result.zip')
            with zipfile.ZipFile(root/'result.zip') as z:
                self.assertEqual(z.read('main.py'),b'x = 2\n'); self.assertNotIn('.env',z.namelist())
            s.undo(); self.assertEqual((s.root/'main.py').read_text(),'x = 1\n')
            with self.assertRaises(SyntaxError): s.preview('main.py','def !!!')
            with self.assertRaises(ValueError): s.export(s.root/'out.zip')
            with zipfile.ZipFile(source) as z: self.assertEqual(z.read('main.py'),b'x = 1\n')

    def test_unsafe_archive_paths(self):
        for name in ['../evil','/absolute','C:/bad','a\\b','CON.txt','x.']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                source=Path(folder)/'input.zip'
                with zipfile.ZipFile(source,'w') as z: z.writestr(name,'bad')
                with self.assertRaises(ValueError): UpdateSession(source,folder)
                self.assertEqual(len(list(Path(folder).iterdir())),1)
