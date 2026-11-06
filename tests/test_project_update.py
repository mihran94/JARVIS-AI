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

    def test_batch_conflict_preflight_and_grouped_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'in.zip'
            with zipfile.ZipFile(source,'w') as z:
                z.writestr('a.py','a=1\n'); z.writestr('b.py','b=1\n')
            s=UpdateSession(source,folder)
            proposals=[s.preview('a.py','a=2\n'),s.preview('b.py','b=2\n')]
            (s.root/'b.py').write_text('b=3\n')
            with self.assertRaises(ValueError): s.apply_batch(proposals)
            self.assertEqual((s.root/'a.py').read_text(),'a=1\n')
            (s.root/'b.py').write_text('b=1\n')
            s.apply_batch(proposals); s.undo()
            self.assertEqual((s.root/'a.py').read_text(),'a=1\n')
            self.assertEqual((s.root/'b.py').read_text(),'b=1\n')

    def test_batch_write_failure_restores_previous_files(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'in.zip'
            with zipfile.ZipFile(source,'w') as z:
                z.writestr('a.py','a=1\n'); z.writestr('b.py','b=1\n')
            s=UpdateSession(source,folder)
            proposals=[s.preview('a.py','a=2\n'),s.preview('b.py','b=2\n')]
            write=s._write
            def fail(path,data):
                if path.name=='b.py' and data==b'b=2\n': raise OSError('simulated')
                write(path,data)
            with patch.object(s,'_write',side_effect=fail), self.assertRaises(OSError): s.apply_batch(proposals)
            self.assertEqual((s.root/'a.py').read_text(),'a=1\n')
            self.assertFalse(s.history)
