import json
from pathlib import Path
import stat
import time
import zipfile
import pytest
from core.updates import inspect_zip, activate_zip, rollback, read_state, release_path, UpdateError

@pytest.fixture
def install(tmp_path):
    root=tmp_path/'install'; root.mkdir()
    (root/'requirements.txt').write_text('pinned==1\n')
    (root/'main.py').write_text('base code')
    (root/'core').mkdir(); (root/'core/store.py').write_text('stable db code')
    return root


def archive(tmp_path,extras=None):
    path=tmp_path/'release.zip'
    files={'main.py':b'new code','requirements.txt':b'pinned==1\n',
           'desktop/app.py':b'new UI','core/store.py':b'stable db code'}
    files.update(extras or {})
    with zipfile.ZipFile(path,'w') as z:
        for name,content in files.items():
            # The member name is written after the ZipInfo is built, because
            # the zip module turns a backslash into a path separator on
            # Windows. An unsafe name has to survive exactly as written on
            # every platform, otherwise the check would not be tested at all.
            item=zipfile.ZipInfo('placeholder')
            item.filename='JARVIS-AI-main/'+name
            item.date_time=time.localtime()[:6]
            z.writestr(item,content)
    return path


def test_update_and_rollback_preserve_original(install,tmp_path):
    path=archive(tmp_path)
    digest,_=inspect_zip(path)
    activate_zip(install,path,digest)
    assert read_state(install)=={'active':digest,'previous':'base'}
    assert (install/'main.py').read_text()=='base code'
    assert (release_path(install,digest)/'main.py').read_text()=='new code'
    rollback(install)
    assert read_state(install)['active']=='base'
    assert (release_path(install,digest)/'main.py').exists()


def test_changed_zip_after_review(install,tmp_path):
    path=archive(tmp_path); digest,_=inspect_zip(path)
    archive(tmp_path,{'main.py':b'different code'})
    with pytest.raises(UpdateError,match='changed after review'): activate_zip(install,path,digest)
    assert read_state(install)['active']=='base'

@pytest.mark.parametrize('name',['../escape.py','/absolute.py','a\\escape.py','CON.py',
                                'a:stream','trailing./x','nested/../x','.venv/x','.env','.updates/x'])
def test_reject_unsafe_archive(tmp_path,name):
    with pytest.raises(UpdateError): inspect_zip(archive(tmp_path,{name:b'x'}))


def test_reject_symlink(tmp_path):
    path=archive(tmp_path)
    with zipfile.ZipFile(path,'a') as z:
        item=zipfile.ZipInfo('JARVIS-AI-main/link')
        item.external_attr=(stat.S_IFLNK|0o777)<<16
        z.writestr(item,'../outside')
    with pytest.raises(UpdateError,match='Links'): inspect_zip(path)

@pytest.mark.parametrize('name', ['requirements.txt','core/store.py'])
def test_compatibility_change_requires_manual_install(install,tmp_path,name):
    path=archive(tmp_path,{name:b'changed'})
    digest,_=inspect_zip(path)
    with pytest.raises(UpdateError): activate_zip(install,path,digest)
    assert read_state(install)['active']=='base'


def test_case_collision(tmp_path):
    path=archive(tmp_path,{'MAIN.py':b'conflict'})
    with pytest.raises(UpdateError,match='case-colliding'): inspect_zip(path)


def test_invalid_state_does_not_escape(install):
    (install/'.updates').mkdir()
    (install/'.updates/state.json').write_text(json.dumps({'active':'../../outside'}))
    with pytest.raises(UpdateError,match='state is invalid'): read_state(install)


def test_failed_pointer_write_retains_current(install,tmp_path,monkeypatch):
    import core.updates as module
    path=archive(tmp_path);digest,_=inspect_zip(path)
    original=module.os.replace
    def fail(source,target):
        if Path(target).name=='state.json': raise OSError('simulated disk error')
        return original(source,target)
    monkeypatch.setattr(module.os,'replace',fail)
    with pytest.raises(OSError): activate_zip(install,path,digest)
    assert read_state(install)['active']=='base'
    assert (install/'main.py').read_text()=='base code'


def test_missing_previous_cannot_rollback(install):
    with pytest.raises(UpdateError,match='No retained'): rollback(install)

@pytest.mark.parametrize('approved',[False,True])
def test_desktop_update_approval(install,tmp_path,monkeypatch,approved):
    from PySide6.QtWidgets import QApplication, QPushButton
    from PySide6.QtCore import QTimer
    from desktop.app import Window
    from desktop.update_dialog import open_updates
    app=QApplication.instance() or QApplication([])
    window=Window(tmp_path/'data')
    path=archive(tmp_path); digest,_=inspect_zip(path)
    monkeypatch.setenv('JARVIS_INSTALL_ROOT',str(install))
    monkeypatch.setattr('desktop.update_dialog.QFileDialog.getOpenFileName',lambda *a:(str(path),''))
    monkeypatch.setattr('desktop.app.QMessageBox.warning',lambda *a:None)
    window.confirm=lambda _:approved
    errors=[]
    def interact():
        dialog=app.activeModalWidget()
        try:
            buttons={b.text():b for b in dialog.findChildren(QPushButton)}
            buttons['Select GitHub ZIP'].click()
            assert buttons['Approve selected update for next startup'].isEnabled()
            buttons['Approve selected update for next startup'].click()
        except BaseException as e: errors.append(e)
        finally: dialog.accept()
    QTimer.singleShot(0,interact)
    open_updates(window)
    if errors: raise errors[0]
    assert read_state(install)['active']==(digest if approved else 'base')
    assert bool(list((tmp_path/'data').glob('history-before-update-*.sqlite3')))==approved
    window.close()


def test_launcher_uses_retained_environment(install,tmp_path,monkeypatch):
    import importlib.util
    spec=importlib.util.spec_from_file_location('launch_test',Path(__file__).parents[1]/'scripts/launch.py')
    launch=importlib.util.module_from_spec(spec); spec.loader.exec_module(launch)
    path=archive(tmp_path); digest,_=inspect_zip(path);activate_zip(install,path,digest)
    monkeypatch.setattr(launch,'ROOT',install)
    captured=[]
    monkeypatch.setattr(launch.subprocess,'call',lambda args,**kw:captured.append((args,kw)) or 0)
    assert launch.main()==0
    assert Path(captured[0][0][1])==release_path(install,digest)/'main.py'
    assert captured[0][1]['env']['JARVIS_INSTALL_ROOT']==str(install)
