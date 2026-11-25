from pathlib import Path

from core.runtime_profile import data_directory
from scripts import launch, verify_windows
from security.vault import Vault


def test_development_profile_uses_checkout_source_and_separate_vault(tmp_path, monkeypatch):
    (tmp_path / 'main.py').touch()
    monkeypatch.setattr(launch, 'ROOT', tmp_path)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.delenv('JARVIS_DEVELOPMENT_PROFILE', raising=False)
    default_service = Vault().service
    default_data = data_directory()
    captured = []

    def run(args, *, cwd, env):
        captured.append(env['JARVIS_DEVELOPMENT_PROFILE'])
        assert args[1:] == [str(tmp_path / 'main.py')]
        assert cwd == tmp_path
        assert env['JARVIS_SOURCE_RELEASE'] == 'base'
        with monkeypatch.context() as child:
            child.setenv('JARVIS_DEVELOPMENT_PROFILE', captured[-1])
            assert data_directory().parent == default_data.with_name('JarvisAI-Development')
            assert Vault().service != default_service
        return 19

    monkeypatch.setattr(launch.subprocess, 'call', run)
    assert launch.main(['--dev-data']) == 19
    assert launch.main(['--dev-data']) == 19
    assert captured[0] == captured[1]
    assert data_directory() == default_data
    assert Vault().service == default_service


def test_smoke_storage_is_disposable_even_after_an_app_failure(tmp_path, monkeypatch):
    (tmp_path / 'main.py').touch()
    monkeypatch.setattr(launch, 'ROOT', tmp_path)
    observed = []

    def run(args, *, cwd, env):
        scratch = Path(env['LOCALAPPDATA'])
        assert scratch.is_dir()
        assert env['JARVIS_DEVELOPMENT_PROFILE']
        (scratch / 'dummy.sqlite3').touch()
        observed.append(scratch)
        return 10

    monkeypatch.setattr(launch.subprocess, 'call', run)
    assert launch.main(['--dev-data', '--smoke-test']) == 10
    assert not observed[0].exists()


def test_offline_verifier_does_not_inherit_live_test_switches(monkeypatch):
    switches = ('JARVIS_AZURE_LIVE_AUDIO', 'JARVIS_BROWSER_ACCEPTANCE', 'GITHUB_ACTIONS')
    for switch in switches:
        monkeypatch.setenv(switch, '1')
    monkeypatch.setenv('JARVIS_DEVELOPMENT_PROFILE', 'a' * 24)
    monkeypatch.setattr(verify_windows.importlib.util, 'find_spec', lambda name: object())
    observed = []

    def run(args, *, cwd, env):
        assert all(switch not in env for switch in switches)
        if args[1:3] == ['-m', 'pytest']:
            assert len(env['JARVIS_DEVELOPMENT_PROFILE']) == 24
            assert env['JARVIS_DEVELOPMENT_PROFILE'] != 'a' * 24
            assert args[-2:] == ['--basetemp', str(Path(env['TEMP']) / 'tests')]
            observed.append(Path(env['TEMP']))
        return 0

    monkeypatch.setattr(verify_windows.subprocess, 'call', run)
    assert verify_windows.run_checks(full=True) == 0
    assert len(observed) == 1
    assert not observed[0].exists()
