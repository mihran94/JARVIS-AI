import io
import json
from types import SimpleNamespace
import pytest
from developer_studio import runner

IMAGE = 'sha256:' + 'a'*64
SOURCE = 'print(42)'


def test_restrictive_command():
    args=runner.container_args('owned',IMAGE)
    for flag in ('--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
                 '--user=65534:65534','--memory=256m','--pids-limit=32','--log-driver=none','--pull=never'):
        assert flag in args
    assert '--privileged' not in args and '--mount' not in args and '-v' not in args
    assert args[-5:]==[IMAGE,'-I','-B','-u','-']

@pytest.mark.parametrize('source,image,digest',[(SOURCE,IMAGE,'wrong'),(SOURCE,'python:latest','wrong'),('',IMAGE,'wrong')])
def test_reject_before_process(monkeypatch,source,image,digest):
    monkeypatch.setattr(runner.shutil,'which',lambda _:pytest.fail('Must not launch'))
    with pytest.raises(runner.RunnerError): runner.run_python(source,image,digest)


def test_missing_docker_no_fallback(monkeypatch):
    monkeypatch.setattr(runner.shutil,'which',lambda _:None)
    with pytest.raises(runner.RunnerError,match='not run on the host'):
        runner.run_python(SOURCE,IMAGE,runner.approval_digest(SOURCE,IMAGE))


class Input(io.BytesIO):
    def close(self): pass

class Process:
    def __init__(self,output,exit_code,hang):
        self.stdin=Input(); self.stdout=io.BytesIO(output)
        self.returncode=None; self.exit_code=exit_code; self.hang=hang; self.killed=False
    def poll(self):
        if not self.hang and self.returncode is None: self.returncode=self.exit_code
        return self.returncode
    def kill(self): self.killed=True; self.returncode=-9
    def wait(self,timeout): return self.returncode

@pytest.mark.parametrize('mode,status',[
    ('success','completed'),('failure','failed'),('overflow','output_limit'),
    ('timeout','timeout'),('cancel','cancelled')])
def test_execution_lifecycle(monkeypatch,mode,status):
    monkeypatch.setattr(runner.shutil,'which',lambda _: '/trusted/docker')
    monkeypatch.setenv('DOCKER_HOST','tcp://remote:2375')
    calls=[]
    def command(args,**kw):
        calls.append(args)
        assert kw['shell'] is False and 'DOCKER_HOST' not in kw['env']
        assert 'tcp://remote:2375' not in args
        if 'inspect' in args:
            return SimpleNamespace(returncode=0,stdout=json.dumps([{'Os':'linux','Config':{}}]).encode())
        return SimpleNamespace(returncode=0,stdout=b'')
    monkeypatch.setattr(runner.subprocess,'run',command)
    process=Process(b'x'*(runner.MAX_OUTPUT+1) if mode=='overflow' else b'42\n',
                    1 if mode=='failure' else 0, mode in ('timeout','cancel'))
    def popen(args,**kw):
        calls.append(args)
        assert SOURCE not in args and kw['shell'] is False
        return process
    monkeypatch.setattr(runner.subprocess,'Popen',popen)
    if mode=='timeout':
        clock=iter([0,21]); monkeypatch.setattr(runner.time,'monotonic',lambda:next(clock))
    checks=[]
    def cancel():
        checks.append(1)
        return mode=='cancel' and len(checks)>=4
    result=runner.run_python(SOURCE,IMAGE,runner.approval_digest(SOURCE,IMAGE),cancel)
    assert result.status==status
    assert len(result.output)<=runner.MAX_OUTPUT
    assert 'rm' in calls[-1] and '--force' in calls[-1]
    assert process.stdin.getvalue()==SOURCE.encode()

@pytest.mark.parametrize('metadata',[{'Os':'windows','Config':{}},{'Os':'linux','Config':{'Volumes':{'/data':{}}}}])
def test_reject_unsupported_image(monkeypatch,metadata):
    monkeypatch.setattr(runner.shutil,'which',lambda _: '/trusted/docker')
    monkeypatch.setattr(runner.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps([metadata]).encode()))
    monkeypatch.setattr(runner.subprocess,'Popen',lambda *a,**k:pytest.fail('No start allowed'))
    with pytest.raises(runner.RunnerError,match='Linux Python image'):
        runner.run_python(SOURCE,IMAGE,runner.approval_digest(SOURCE,IMAGE))


def test_cleanup_failure_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(runner.shutil,'which',lambda _: '/trusted/docker')
    def command(args,**kw):
        if 'inspect' in args:
            return SimpleNamespace(returncode=0,stdout=b'[{"Os":"linux","Config":{}}]')
        return SimpleNamespace(returncode=1 if 'rm' in args else 0,stdout=b'')
    monkeypatch.setattr(runner.subprocess,'run',command)
    monkeypatch.setattr(runner.subprocess,'Popen',lambda *a,**k:Process(b'ok',0,False))
    with pytest.raises(runner.RunnerError,match='cleanup could not be confirmed'):
        runner.run_python(SOURCE,IMAGE,runner.approval_digest(SOURCE,IMAGE))


def test_start_failure_still_requests_cleanup(monkeypatch):
    monkeypatch.setattr(runner.shutil,'which',lambda _: '/trusted/docker')
    calls=[]
    def command(args,**kw):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout=b'[{"Os":"linux","Config":{}}]')
    def fail(*a,**kw): raise OSError('private details')
    monkeypatch.setattr(runner.subprocess,'run',command)
    monkeypatch.setattr(runner.subprocess,'Popen',fail)
    with pytest.raises(runner.RunnerError,match='Docker execution failed'):
        runner.run_python(SOURCE,IMAGE,runner.approval_digest(SOURCE,IMAGE))
    assert 'rm' in calls[-1]
