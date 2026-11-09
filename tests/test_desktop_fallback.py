import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
import httpx
from PySide6.QtWidgets import QApplication
import desktop.app as desktop
from providers.chat import stream_chat, ProviderError, TransientProviderError
from providers.stream_fallback import StreamTarget
from security.policy import Policy

@pytest.mark.parametrize('code,retryable', [(401,False),(403,False),(429,False),(500,False),(502,True),(503,True),(504,True)])
def test_http_retry_classification(code,retryable):
    with pytest.raises(ProviderError) as error:
        stream_chat('OpenAI','test','fake',[{'role':'user','content':'hi'}],lambda:None,lambda _:None,
                    transport=httpx.MockTransport(lambda _:httpx.Response(code)))
    assert isinstance(error.value,TransientProviderError) is retryable

@pytest.mark.parametrize('case,expected,status',[
    ('backup',['OpenAI','Gemini'],'completed'),
    ('no_consent',['OpenAI'],'failed'),
    ('auth',['OpenAI'],'failed'),
    ('partial',['OpenAI'],'failed'),
    ('stop',[],'cancelled'),
])
def test_worker_boundaries(monkeypatch,case,expected,status):
    app=QApplication.instance() or QApplication([])
    policy=Policy(); calls=[]; results=[]
    def stream(provider,model,key,messages,check,emit,metrics):
        check(); calls.append(provider)
        if provider=='OpenAI':
            if case=='partial': emit('partial')
            if case=='auth': raise ProviderError('auth failed')
            raise TransientProviderError('temporary')
        metrics['total_tokens']=7
        emit('complete'); return 'complete'
    monkeypatch.setattr(desktop,'stream_chat',stream)
    worker=desktop.ChatWorker('OpenAI','primary','fake',[{'role':'user','content':'hi'}],policy,policy.ticket(),
                              backup=None if case=='no_consent' else StreamTarget('Gemini','secondary','fake'))
    worker.result.connect(lambda *args:results.append(args))
    if case=='stop': policy.stop()
    worker.run()
    assert calls==expected and results[0][0]==status
    assert worker.key=='' and worker.backup is None
    if case=='backup':
        assert results[0][2]['provider']=='Gemini'
        assert results[0][2]['model']=='secondary'
        assert results[0][2]['total_tokens']==7


def test_consent_consumed(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    window=desktop.Window(tmp_path)
    assert not window.backup_consent.isChecked()
    monkeypatch.setattr(window,'get_key',lambda _: 'fake')
    captured=[]
    monkeypatch.setattr(window,'start_worker',lambda *args,**kw:captured.append(kw))
    window.backup_consent.setChecked(True)
    window.prompt.setPlainText('hi'); window.send()
    assert captured[0]['backup'].name=='MiniMax'
    assert not window.backup_consent.isChecked()
    window.close()


def test_probe_does_not_receive_backup(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    window=desktop.Window(tmp_path)
    monkeypatch.setattr(desktop.ChatWorker,'start',lambda self:None)
    window.chat_ticket=window.policy.ticket()
    window.start_worker('OpenAI','primary','fake',[], 'provider_check',
                        backup=StreamTarget('Gemini','secondary','fake'))
    assert window.worker.backup is None
    window.on_finished()
    window.close()
