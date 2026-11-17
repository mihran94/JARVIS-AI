import pytest
from PySide6.QtWidgets import QApplication
from desktop.app import Window
from security.policy import Action
from developer_studio.generation import messages_for_goal, prepare_draft

# The short names keep the test id small, because pytest puts the test id in
# an environment variable and Windows refuses a value longer than 32767
# characters.
@pytest.mark.parametrize('goal',['', ' '*3, 'x'*20001],
                         ids=['empty-goal','blank-goal','oversized-goal'])
def test_invalid_goal(goal):
    with pytest.raises(ValueError): messages_for_goal(goal)


def test_draft_validation_does_not_execute(tmp_path):
    target=tmp_path/'not-created'
    source=f'from pathlib import Path\nPath({str(target)!r}).touch()'
    draft, report=prepare_draft('```python\n'+source+'\n```')
    assert draft==source and 'passed' in report and not target.exists()
    assert 'failed' in prepare_draft('def broken(')[1]

@pytest.mark.parametrize('allow,stop,provider', [
    (False, False, 'MiniMax'), (True, False, 'MiniMax'), (True, True, 'MiniMax'),
    (True, False, 'Codex'),
])
def test_generation_review_boundary(tmp_path,monkeypatch,allow,stop,provider):
    app=QApplication.instance() or QApplication([])
    window=Window(tmp_path)
    # Only MiniMax and Codex may write code; the chat provider is never
    # used for it, whatever it is set to.
    window.coding_provider.setCurrentText(provider)
    assert window.store.get('coding_provider') == provider
    assert window.chat_provider.currentText() == 'Gemini'
    original=window.editor.toPlainText()
    monkeypatch.setattr(window,'get_key',lambda _: 'fake')
    window.code_goal.setText('Create a calculator')
    calls=[]
    def start(provider,model,key,messages,kind):
        assert provider == expected_provider
        calls.append(messages)
        window.worker_kind=kind
        window.active_provider=provider; window.active_model=model
        window.chat_task=window.store.task(kind,'test')
        if stop: window.policy.stop()
        window.on_result('completed','print(42)',{})
    expected_provider = provider
    monkeypatch.setattr(window,'start_worker',start)
    def codex_draft(prompt,kind):
        # Codex is the command line tool, so it has its own path; the
        # approval and the review boundary are the same.
        if not window.confirm(Action('codex_draft','test')):
            return
        calls.append(prompt)
        window.worker_kind=kind
        window.chat_ticket=window.policy.ticket()
        window.chat_task=window.store.task(kind,'test')
        if stop: window.policy.stop()
        window.on_codex_result('completed','print(42)')
    monkeypatch.setattr(window,'draft_with_codex',codex_draft)
    monkeypatch.setattr('desktop.app.QMessageBox.warning',lambda *args:None)
    window.confirm=lambda _:allow
    window.generate_code()
    assert len(calls)==int(allow)
    assert window.editor.toPlainText()==original
    assert window.store.messages(window.session)==[]
    assert not list(window.workspace.root.glob('*.py'))
    if allow and not stop:
        assert window.code_preview.toPlainText()=='print(42)'
        assert 'Create a calculator' in str(calls[0])
        assert original not in str(calls)
        window.confirm=lambda _:False
        window.apply_code_draft()
        assert window.editor.toPlainText()==original
        window.confirm=lambda _:True
        window.apply_code_draft()
        assert window.editor.toPlainText()=='print(42)'
        assert window.editor.document().isModified()
        assert not list(window.workspace.root.glob('*.py'))
    elif stop:
        assert window.code_preview.toPlainText()==''
    window.editor.document().setModified(False)
    window.close()
