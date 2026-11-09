import pytest
from PySide6.QtWidgets import QApplication
from desktop.app import Window
from providers.chat import PROVIDERS

@pytest.mark.parametrize('provider',list(PROVIDERS))
def test_key_only_save(tmp_path, provider):
    app=QApplication.instance() or QApplication([])
    window=Window(tmp_path)
    saved={}
    class Vault:
        def put(self,name,key): saved[name]=key
        def get(self,name): return saved.get(name,'')
    window.vault=Vault()
    window.provider.setCurrentText(provider)
    assert window.provider_advanced_panel.isHidden()
    window.secret.setText('fake-key')
    window.save_provider()
    assert saved=={provider:'fake-key'}
    assert window.store.get('model:'+provider)==PROVIDERS[provider].default_model
    assert window.chat_provider.currentText()==provider
    assert window.secret.text()=='' and window.worker is None
    window.close()


def test_custom_model_preserved_and_reset(tmp_path):
    app=QApplication.instance() or QApplication([])
    window=Window(tmp_path)
    window.store.set('model:OpenAI','custom-model')
    window.load_provider()
    assert window.model.text()=='custom-model'
    window.advanced_provider.setChecked(True)
    assert not window.provider_advanced_panel.isHidden()
    window.reset_provider_model()
    assert window.model.text()==PROVIDERS['OpenAI'].default_model
    window.close()
