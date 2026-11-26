import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest

spec = importlib.util.spec_from_file_location('diagnose', Path(__file__).parents[1] / 'scripts' / 'diagnose.py')
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)

@pytest.fixture
def installed(monkeypatch, tmp_path):
    (tmp_path / 'requirements.txt').write_text('httpx==0.28.1\n')
    monkeypatch.setattr(diag, 'ROOT', tmp_path)
    monkeypatch.setattr(diag.sys, 'platform', 'win32')
    monkeypatch.setattr(diag.sys, 'version_info', (3,12,0))
    monkeypatch.setattr(diag.struct, 'calcsize', lambda _:8)
    monkeypatch.setattr(diag.importlib.metadata, 'version', lambda _: '0.28.1')
    monkeypatch.setattr(diag, 'probe_imports', lambda: (True,'ok'))


def test_ready( installed):
    assert diag.collect()['ready']


def test_missing_package(installed, monkeypatch):
    def missing(_): raise diag.importlib.metadata.PackageNotFoundError('secret-never-print')
    monkeypatch.setattr(diag.importlib.metadata,'version',missing)
    report=diag.collect()
    assert not report['ready']
    assert 'secret-never-print' not in str(report)


def test_wrong_version(installed, monkeypatch):
    monkeypatch.setattr(diag.importlib.metadata,'version',lambda _: '0.0')
    assert not diag.collect()['ready']


def test_non_windows(installed, monkeypatch):
    monkeypatch.setattr(diag.sys,'platform','linux')
    assert not diag.collect()['ready']

@pytest.mark.parametrize('outcome',[0,1,'timeout','spawn'])
def test_bounded_child(monkeypatch,outcome):
    def run(args,**kwargs):
        assert args[1]=='-I' and kwargs['timeout']==20
        assert kwargs['stderr']==subprocess.DEVNULL
        if outcome=='timeout': raise subprocess.TimeoutExpired(args,20)
        if outcome=='spawn': raise OSError('private path')
        return SimpleNamespace(returncode=outcome)
    monkeypatch.setattr(diag.subprocess,'run',run)
    ok,message=diag.probe_imports()
    assert ok == (outcome==0)
    assert 'private path' not in message


def test_default_does_not_probe_ollama(installed, monkeypatch, capsys):
    def unexpected(_):
        pytest.fail('default diagnostics contacted Ollama')
    monkeypatch.setattr(diag, 'probe_local_model', unexpected)
    assert diag.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['ready']
    assert all('Ollama' not in check['name'] for check in report['checks'])


@pytest.mark.parametrize('installed_ok,listed,code', [
    (True, True, 0), (True, False, 1), (False, True, 1),
])
def test_requested_listing_contributes_to_exit_status(monkeypatch, capsys,
                                                      installed_ok, listed, code):
    monkeypatch.setattr(diag, 'collect', lambda: {
        'ready': installed_ok, 'checks': [], 'limitations': 'Installation check only.',
    })

    def probe(tag):
        assert tag == 'qwen3:8b'
        return listed, 'listing result'

    monkeypatch.setattr(diag, 'probe_local_model', probe)
    assert diag.main(['--local-model', 'qwen3:8b']) == code
    report = json.loads(capsys.readouterr().out)
    assert report['ready'] == (code == 0)
    assert report['checks'] == [{
        'name': 'Local Ollama model listing',
        'status': 'pass' if listed else 'fail',
        'detail': 'listing result',
    }]
    assert 'does not verify model generation' in report['limitations']
