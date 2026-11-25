"""Regression coverage for private project files and available OS metrics."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import json
import subprocess

import pytest

from core.protection import Protection, dropped_data, ignore_patterns, is_ignored


@pytest.fixture
def project(tmp_path):
    """A project with a secret, a gitignored file and ordinary code."""
    folder = tmp_path / 'project'
    folder.mkdir()
    (folder / '.gitignore').write_text(
        '# local settings\nlocal_settings.json\ndata/\n*.log\n', encoding='utf-8')
    (folder / 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    (folder / '.env').write_text('OPENAI_API_KEY=sk-not-a-real-key\n', encoding='utf-8')
    (folder / 'config').mkdir()
    (folder / 'config' / 'api_keys.json').write_text('{"openai": "sk-not-a-real-key"}',
                                                     encoding='utf-8')
    (folder / 'secrets.yaml').write_text('token: abc\n', encoding='utf-8')
    (folder / 'local_settings.json').write_text('{"theme": "dark"}', encoding='utf-8')
    (folder / 'notes.log').write_text('a log line\n', encoding='utf-8')
    (folder / 'data').mkdir()
    (folder / 'data' / 'users.json').write_text('{"user": "someone"}', encoding='utf-8')
    return folder


# ── which files are off limits ───────────────────────────────────────────────

def test_a_file_of_secrets_is_off_limits(project):
    protection = Protection(project)
    assert protection.blocked('.env')
    assert protection.blocked('config/api_keys.json')
    assert protection.blocked('secrets.yaml')
    assert 'secret' in protection.reason('config/api_keys.json')


def test_a_gitignored_file_is_off_limits(project):
    protection = Protection(project)
    assert protection.blocked('local_settings.json')
    assert protection.blocked('notes.log')
    assert protection.blocked('data/users.json')
    assert '.gitignore' in protection.reason('local_settings.json')


def test_ordinary_source_is_not_off_limits(project):
    protection = Protection(project)
    assert not protection.blocked('app.py')
    assert protection.reason('app.py') == ''


def test_source_code_named_like_a_secret_is_still_editable(project):
    """A project may well have code called api_keys.py."""
    protection = Protection(project)
    assert not protection.blocked('api_keys.py')
    assert not protection.blocked('token_utils.py')


def test_the_protected_files_are_listed(project):
    protection = Protection(project)
    found = protection.protected_files()
    assert 'config/api_keys.json' in found
    assert '.env' in found
    assert 'local_settings.json' in found
    assert 'app.py' not in found


def test_the_notice_names_the_off_limits_files(project):
    protection = Protection(project)
    notice = protection.notice()
    assert 'off limits' in notice
    assert 'config/api_keys.json' in notice


def test_the_gitignore_patterns_are_read_and_negations_are_ignored(tmp_path):
    folder = tmp_path / 'p'
    folder.mkdir()
    (folder / '.gitignore').write_text('*.log\n!keep.log\n# comment\ndata/\n', encoding='utf-8')
    patterns = ignore_patterns(folder)
    assert '*.log' in patterns
    assert 'data/' in patterns
    assert '!keep.log' not in patterns
    assert is_ignored('a/b.log', patterns)
    assert is_ignored('data/x.json', patterns)


# ── the project context leaves the secrets behind ───────────────────────────

def test_the_project_context_never_carries_a_key(project):
    from core.coding_agent import project_context
    context = project_context(project)
    assert 'def main' in context
    assert 'sk-not-a-real-key' not in context
    assert 'api_keys.json' not in context
    assert '.env' not in context
    assert 'local_settings.json' not in context


def test_a_protected_file_may_not_be_written(project):
    from core.coding_agent import CodingAgentError, apply_files
    with pytest.raises(CodingAgentError, match='protected'):
        apply_files(project, {'config/api_keys.json': '{"openai": "changed"}'})
    # A reserved path is refused as well; the message says which rule it was.
    with pytest.raises(CodingAgentError, match='reserved path|protected'):
        apply_files(project, {'.env': 'OPENAI_API_KEY=other'})
    # The file on disk is untouched.
    assert (project / 'config' / 'api_keys.json').read_text(encoding='utf-8') == \
        '{"openai": "sk-not-a-real-key"}'


def test_an_ordinary_file_may_still_be_written(project):
    from core.coding_agent import apply_files
    written = apply_files(project, {'app.py': 'def main():\n    return 2\n'})
    assert written == ['app.py']
    assert 'return 2' in (project / 'app.py').read_text(encoding='utf-8')


# ── the Codex task ──────────────────────────────────────────────────────────

def test_the_codex_prompt_names_the_off_limits_files(project):
    from developer_studio.codex_task import build_prompt
    prompt = build_prompt(type('P', (), {'name': 'project-a'})(), 'fix the login',
                           Protection(project))
    assert 'off limits' in prompt
    assert 'config/api_keys.json' in prompt


def test_a_change_to_a_protected_file_is_put_back_and_left_out_of_the_diff(tmp_path):
    """The review screen must never show the contents of a key."""
    from developer_studio.codex_task import CodexTask

    folder = tmp_path / 'repo'
    folder.mkdir()
    subprocess.run(['git', '-C', str(folder), 'init', '-b', 'main'],
                   capture_output=True, check=True)
    subprocess.run(['git', '-C', str(folder), 'config', 'user.email', 't@e.com'],
                   capture_output=True, check=True)
    subprocess.run(['git', '-C', str(folder), 'config', 'user.name', 'T'],
                   capture_output=True, check=True)
    (folder / '.gitignore').write_text('local_settings.json\n', encoding='utf-8')
    (folder / 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    (folder / 'config').mkdir()
    (folder / 'config' / 'api_keys.json').write_text('{"openai": "sk-not-a-real-key"}',
                                                     encoding='utf-8')
    subprocess.run(['git', '-C', str(folder), 'add', '-A'], capture_output=True, check=True)
    subprocess.run(['git', '-C', str(folder), 'commit', '-m', 'first'],
                   capture_output=True, check=True)

    task = CodexTask(type('P', (), {'name': 'project-a', 'path': str(folder)})(), 'change it')
    worktree = folder.parent / 'worktree'
    worktree.mkdir()
    # A worktree that holds the same files, with the secret changed and the
    # code changed too.
    subprocess.run(['git', '-C', str(folder), 'worktree', 'add', '--detach', str(worktree),
                    'HEAD'], capture_output=True, check=True)
    (worktree / 'config' / 'api_keys.json').write_text('{"openai": "sk-leaked"}',
                                                         encoding='utf-8')
    (worktree / 'app.py').write_text('def main():\n    return 2\n', encoding='utf-8')

    diff, changed, refused = task._collect_diff(worktree)
    assert 'config/api_keys.json' in refused
    assert 'config/api_keys.json' not in changed
    assert 'sk-leaked' not in diff
    assert 'app.py' in changed
    # The file was put back in the worktree.
    assert 'sk-not-a-real-key' in (worktree / 'config' / 'api_keys.json').read_text(
        encoding='utf-8')


# ── the data-loss check ─────────────────────────────────────────────────────

def test_an_edit_that_drops_a_setting_is_reported():
    old = json.dumps({'openai': 'x', 'gemini': 'y', 'theme': 'dark'})
    new = json.dumps({'openai': 'x'})
    lost = dropped_data('config.json', old, new)
    assert 'gemini' in lost
    assert 'theme' in lost
    assert dropped_data('config.json', old, old) == ''


def test_a_file_that_is_not_a_settings_file_is_not_checked():
    assert dropped_data('app.py', 'a = 1\n', 'a = 2\n') == ''


# ── the GPU and the temperature ─────────────────────────────────────────────

def test_the_gpu_and_the_temperature_are_unavailable_when_they_cannot_be_read(monkeypatch):
    import desktop.system_metrics as metrics
    monkeypatch.setattr(metrics, 'cpu_temperature', lambda: None)
    data = metrics.snapshot()
    assert data['gpu_usage_percent'] is None
    assert data['cpu_temperature_c'] is None
    text = metrics.format_snapshot(data)
    assert 'GPU  /  Unavailable' in text
    assert 'CPU TEMPERATURE  /  Unavailable' in text


def test_available_temperature_is_reported(monkeypatch):
    import desktop.system_metrics as metrics
    monkeypatch.setattr(metrics, 'cpu_temperature', lambda: 61.5)
    data = metrics.snapshot()
    assert data['cpu_temperature_c'] == 61.5
    text = metrics.format_snapshot(data)
    assert '61.5 °C' in text


def test_temperature_stays_unavailable_without_supported_sensor(monkeypatch):
    import desktop.system_metrics as metrics
    monkeypatch.setattr(metrics.psutil, 'sensors_temperatures', lambda: {}, raising=False)
    assert metrics.cpu_temperature() is None
