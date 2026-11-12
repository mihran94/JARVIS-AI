import pytest
from PySide6.QtWidgets import QApplication
from desktop.app import Window
from developer_studio.generation import messages_for_repair

# The short names keep the test id small. Windows refuses an environment
# variable longer than 32767 characters, and pytest puts the test id in one.
@pytest.mark.parametrize('source,error',[('', 'error'),('x'*50001,'error'),('pass',''),('pass','x'*10001)],
                         ids=['empty-source','oversized-source','empty-error','oversized-error'])
def test_repair_bounds(source,error):
    with pytest.raises(ValueError): messages_for_repair(source,error)

@pytest.mark.parametrize('mode',['decline','approve','stop_during_approval','late_stop','failure'])
def test_repair_approval_and_result(tmp_path,monkeypatch,mode):
    app=QApplication.instance() or QApplication([])
    window=Window(tmp_path)
    window.editor.setPlainText('print(missing)')
    window.code_error.setPlainText('NameError: missing')
    window.code_preview.setPlainText('old draft')
    monkeypatch.setattr('desktop.app.QMessageBox.warning',lambda *args:None)
    monkeypatch.setattr(window,'get_key',lambda _: 'fake-key')
    approvals=[]; calls=[]
    def confirm(action):
        approvals.append(action)
        if mode=='stop_during_approval': window.policy.stop()
        return mode!='decline'
    window.confirm=confirm
    def start(provider,model,key,messages,kind):
        calls.append((messages,kind))
        window.worker_kind=kind
        window.active_provider=provider; window.active_model=model
        window.chat_task=window.store.task(kind,'test')
        if mode=='late_stop': window.policy.stop()
        window.on_result('failed' if mode=='failure' else 'completed','print(42)',{})
    monkeypatch.setattr(window,'start_worker',start)
    window.repair_code()
    assert approvals[0].kind=='send_editor_code_and_error'
    assert approvals[0].digest
    assert window.editor.toPlainText()=='print(missing)'
    assert window.store.messages(window.session)==[]
    assert not list(window.workspace.root.glob('*.py'))
    if mode in ('decline','stop_during_approval'):
        assert calls==[] and window.code_preview.toPlainText()=='old draft'
    else:
        assert calls[0][1]=='code_repair'
        assert calls[0][0][-1]['content']=='SOURCE:\nprint(missing)\n\nREPORTED ERROR:\nNameError: missing'
        assert window.code_preview.toPlainText()==('print(42)' if mode=='approve' else '')
        assert window.store.tasks()[0]['status']==({'late_stop':'cancelled','failure':'failed'}.get(mode,'completed'))
    window.editor.document().setModified(False)
    window.close()
