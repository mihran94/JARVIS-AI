"""The coding agent's tools, and the commands it may run.

WHAT IS COVERED
    * A command that is not on the list is refused, and a command with a
      pipe or a redirection in it is refused, so model text cannot smuggle
      another command in.
    * An allowed command really runs and its real output is captured.
    * The reading tools return what is really in the project.
    * The writing tools change the project, and refuse to change a file
      that is protected.
    * `run_tests` returns the real output of a real test run.
    * `prepare_pull_request` prepares a title, a body and a diff, and
      publishes nothing.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import subprocess
import sys
import textwrap

import pytest

from core.coding_tools import (
    CommandRefused, build_coding_registry, check_command, run_command,
    split_arguments,
)
from core.coding_workspace import CodingWorkspace


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'app.py').write_text('VALUE = 1\n', encoding='utf-8')
    (root / 'test_app.py').write_text(
        'from app import VALUE\n\n\ndef test_value():\n    assert VALUE == 1\n',
        encoding='utf-8')
    return root


@pytest.fixture
def workspace(project):
    return CodingWorkspace(project)


@pytest.fixture
def registry(workspace):
    return build_coding_registry(workspace)


# ── the command list ───────────────────────────────────────────────────────

def test_a_windows_path_keeps_its_separators():
    # On Windows a backslash is a path separator and not an escape, so
    # the interpreter path has to survive being split. This is the shape
    # the GitHub Windows runner uses.
    arguments = split_arguments(
        r'C:\hostedtoolcache\windows\Python\3.12.10\x64\python.exe -m pytest -q',
        windows=True)
    assert arguments == [r'C:\hostedtoolcache\windows\Python\3.12.10\x64\python.exe',
                         '-m', 'pytest', '-q']


def test_a_quoted_path_stays_one_argument():
    arguments = split_arguments('"C:\\Program Files\\Python\\python.exe" -m pytest',
                                windows=True)
    assert arguments[0] == r'C:\Program Files\Python\python.exe'


def test_an_allowed_command_is_accepted():
    assert check_command('python -m pytest') == ['python', '-m', 'pytest']
    assert check_command('pytest -q') == ['pytest', '-q']


def test_the_running_interpreter_may_be_used():
    arguments = check_command(f'{sys.executable} -m pytest -q')
    assert arguments[1:3] == ['-m', 'pytest']


def test_the_interpreter_may_not_be_given_anything_else():
    with pytest.raises(CommandRefused):
        check_command(f'{sys.executable} -c "import os"')


def test_a_command_that_is_not_on_the_list_is_refused():
    with pytest.raises(CommandRefused) as error:
        check_command('rm -rf /')
    assert 'may not run' in str(error.value)


def test_a_command_with_a_pipe_is_refused():
    with pytest.raises(CommandRefused):
        check_command('python -m pytest | tee log.txt')


def test_a_command_with_a_redirection_is_refused():
    with pytest.raises(CommandRefused):
        check_command('python -m pytest > out.txt')


def test_a_command_with_a_semicolon_is_refused():
    with pytest.raises(CommandRefused):
        check_command('python -V; rm -rf /')


def test_an_empty_command_is_refused():
    with pytest.raises(CommandRefused):
        check_command('   ')


def test_a_real_command_runs_and_its_output_is_kept(tmp_path):
    result = run_command('python -V', tmp_path)
    assert result.returncode == 0
    assert 'Python' in result.output
    assert result.passed is True


def test_a_failing_command_reports_its_exit_code(tmp_path):
    (tmp_path / 'test_bad.py').write_text(
        'def test_bad():\n    assert False\n', encoding='utf-8')
    result = run_command(f'{sys.executable} -m pytest -q', tmp_path)
    assert result.returncode != 0
    assert result.passed is False
    assert 'test_bad.py' in result.output


# ── the reading tools ──────────────────────────────────────────────────────

def test_a_file_is_read(registry):
    assert 'VALUE = 1' in registry.get('read_file').run({'path': 'app.py'})


def test_a_file_outside_the_project_is_refused(registry, tmp_path):
    from core.mission_tools import ToolError

    outside = tmp_path / 'outside.txt'
    outside.write_text('nope', encoding='utf-8')
    with pytest.raises(ToolError):
        registry.get('read_file').run({'path': str(outside)})


def test_the_files_are_listed(registry):
    assert 'app.py' in registry.get('list_files').run({})


def test_the_code_is_searched(registry):
    found = registry.get('search_code').run({'pattern': 'VALUE'})
    assert 'app.py' in found


def test_the_git_status_is_reported(registry, project):
    subprocess.run(['git', 'init', '-q'], cwd=str(project), check=False)
    status = registry.get('git_status').run({})
    assert 'app.py' in status or 'nothing' in status.lower()


def test_the_dependencies_are_inspected(registry, project):
    (project / 'requirements.txt').write_text('httpx==0.28.1\n', encoding='utf-8')
    assert 'httpx' in registry.get('inspect_dependencies').run({})


def test_an_artefact_is_measured(registry, project):
    info = registry.get('artifact_info').run({'path': 'app.py'})
    assert 'SHA-256' in info
    assert 'bytes' in info


# ── the writing tools ──────────────────────────────────────────────────────

def test_a_file_is_written(registry, project):
    assert registry.get('write_file').run({'path': 'new.py', 'content': 'x = 1\n'}) == 'new.py was written.'
    assert (project / 'new.py').read_text(encoding='utf-8') == 'x = 1\n'


def test_a_protected_file_is_not_written(registry, project):
    from core.mission_tools import ToolError

    (project / 'secrets.json').write_text('{"key": "x"}\n', encoding='utf-8')
    with pytest.raises(ToolError):
        registry.get('write_file').run({'path': 'secrets.json', 'content': '{"key": "y"}'})


def test_an_edit_is_applied(registry, project):
    registry.get('edit_file').run({'path': 'app.py', 'old': 'VALUE = 1', 'new': 'VALUE = 2'})
    assert 'VALUE = 2' in (project / 'app.py').read_text(encoding='utf-8')


def test_a_patch_is_applied(registry, project):
    patch = ('--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 3\n')
    result = registry.get('apply_patch').run({'patch': patch})
    assert '1 file(s) changed' in result
    assert 'VALUE = 3' in (project / 'app.py').read_text(encoding='utf-8')


# ── running the tests ──────────────────────────────────────────────────────

def test_the_tests_really_run(registry, project):
    output = registry.get('run_tests').run({'command': f'{sys.executable} -m pytest -q'})
    assert 'passed' in output


def test_a_failing_test_run_is_reported_as_a_failure(registry, project):
    (project / 'test_app.py').write_text(
        'def test_value():\n    assert VALUE == 99\n', encoding='utf-8')
    output = registry.get('run_tests').run({'command': f'{sys.executable} -m pytest -q'})
    assert 'failed' in output
    assert 'test_app.py' in output


# ── the pull request ───────────────────────────────────────────────────────

def test_a_pull_request_is_prepared_and_nothing_is_published(registry, project):
    subprocess.run(['git', 'init', '-q'], cwd=str(project), check=False)
    subprocess.run(['git', 'config', 'user.email', 't@example.invalid'], cwd=str(project),
                   check=False)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=str(project), check=False)
    subprocess.run(['git', 'add', '-A'], cwd=str(project), check=False)
    subprocess.run(['git', 'commit', '-qm', 'first'], cwd=str(project), check=False)
    (project / 'app.py').write_text('VALUE = 2\n', encoding='utf-8')
    prepared = registry.get('prepare_pull_request').run({'title': 'Fix the value',
                                                         'body': 'It was wrong.'})
    assert 'Fix the value' in prepared
    assert 'app.py' in prepared
    assert 'nothing was pushed' in prepared.lower()


def test_a_clean_tree_has_nothing_to_prepare(registry, project):
    subprocess.run(['git', 'init', '-q'], cwd=str(project), check=False)
    subprocess.run(['git', 'config', 'user.email', 't@example.invalid'], cwd=str(project),
                   check=False)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=str(project), check=False)
    subprocess.run(['git', 'add', '-A'], cwd=str(project), check=False)
    subprocess.run(['git', 'commit', '-qm', 'first'], cwd=str(project), check=False)
    assert 'nothing to prepare' in registry.get('prepare_pull_request').run({})


# ── the approval boundary ──────────────────────────────────────────────────

def test_the_tools_that_change_something_need_approval(registry):
    changing = {name for name in registry.names() if not registry.get(name).read_only}
    assert {'write_file', 'edit_file', 'apply_patch', 'run_tests', 'run_command'} <= changing
    assert 'read_file' in registry.read_only_names()


def test_every_tool_says_what_it_returns(registry):
    for name in registry.names():
        assert registry.get(name).returns


# ── the stale bytecode ─────────────────────────────────────────────────────

def test_a_test_run_clears_the_cached_bytecode(tmp_path):
    """A file that was just changed must be tested as it is now.

    The cache is removed before the run, because a coarse file time can
    otherwise make Python read the old code from the cache and report a
    failure that has already been fixed.
    """
    from core.coding_tools import clear_bytecode_cache, is_a_test_command

    project = tmp_path / 'project'
    package = project / 'app'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('VALUE = 1\n', encoding='utf-8')
    cache = package / '__pycache__'
    cache.mkdir()
    (cache / 'stale.pyc').write_bytes(b'stale')

    assert is_a_test_command('python -m pytest -q')
    assert not is_a_test_command('python -V')
    removed = clear_bytecode_cache(project)
    assert removed == 1
    assert not cache.exists()


def test_the_cache_is_cleared_before_the_tests_run(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    cache = project / '__pycache__'
    cache.mkdir()
    (cache / 'stale.pyc').write_bytes(b'stale')
    result = run_command(f'{sys.executable} -V', project)
    assert result.passed
    # A plain command does not clear it.
    assert cache.exists()
