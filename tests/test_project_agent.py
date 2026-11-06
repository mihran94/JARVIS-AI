import json, tempfile, unittest, zipfile
from pathlib import Path
from core.project_update import UpdateSession
from core.project_agent import propose_changes

class AgentTests(unittest.TestCase):
    def test_multi_file_draft_apply_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/'in.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('a.py','x=1\n'); z.writestr('b.py','y=1\n')
            session=UpdateSession(archive,folder)
            changes={'changes':[{'path':'a.py','content':'x=2\n'},{'path':'b.py','content':'y=2\n'}]}
            proposals=propose_changes(session,['a.py','b.py'],'Change values',lambda _:json.dumps(changes))
            self.assertEqual((session.root/'a.py').read_text(),'x=1\n')
            session.apply_batch(proposals); session.undo()
            self.assertEqual((session.root/'b.py').read_text(),'y=1\n')
            for response in ['bad json',json.dumps({'changes':[{'path':'../escape.py','content':'x=2'}]}),json.dumps({'changes':[{'path':'a.py','content':'def !!!'}]})]:
                with self.assertRaises((ValueError,SyntaxError)):
                    propose_changes(session,['a.py'],'Fix',lambda _, r=response:r)
            self.assertEqual((session.root/'a.py').read_text(),'x=1\n')
