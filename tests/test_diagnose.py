import importlib.util
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
