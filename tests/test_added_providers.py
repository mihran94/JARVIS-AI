import json
import httpx
import pytest
from providers.chat import PROVIDERS, stream_chat, ProviderError

NEW = ['DeepSeek', 'Groq', 'OpenRouter']

@pytest.mark.parametrize('name',NEW)
def test_provider_stream_and_usage(name):
    seen=[]; metrics={}; chunks=[]
    def respond(request):
        seen.append(request)
        assert str(request.url)==PROVIDERS[name].endpoint
        assert request.headers['Authorization']=='Bearer fake-test-key'
        body=json.loads(request.content)
        assert body['model']=='chosen-model' and body['stream'] is True
        assert 'tools' not in body
        return httpx.Response(200,text=(
            'data: {"choices":[{"delta":{"content":"Vanakkam"}}]}\n\n'
            'data: {"choices":[],"usage":{"total_tokens":12}}\n\n'
            'data: [DONE]\n\n'))
    result=stream_chat(name,'chosen-model','fake-test-key',[{'role':'user','content':'hi'}],
                       lambda:None,chunks.append,transport=httpx.MockTransport(respond),metrics=metrics)
    assert result=='Vanakkam' and chunks==['Vanakkam']
    assert metrics['total_tokens']==12 and len(seen)==1

@pytest.mark.parametrize('name',NEW)
def test_provider_auth_error_never_contains_body(name):
    with pytest.raises(ProviderError) as error:
        stream_chat(name,'chosen','fake',[{'role':'user','content':'hi'}],lambda:None,lambda _:None,
                    transport=httpx.MockTransport(lambda _:httpx.Response(401,text='private-secret')))
    assert 'private-secret' not in str(error.value)


def test_openrouter_requires_explicit_model():
    assert PROVIDERS['OpenRouter'].default_model==''
    with pytest.raises(ProviderError,match='Configure'):
        stream_chat('OpenRouter','','fake',[],lambda:None,lambda _:None)


def test_all_selectors_include_new_providers(tmp_path):
    from PySide6.QtWidgets import QApplication
    from desktop.app import Window
    app=QApplication.instance() or QApplication([])
    window=Window(tmp_path)
    for combo in (window.provider,window.chat_provider,window.backup_provider):
        assert all(combo.findText(name)>=0 for name in NEW)
    window.close()
