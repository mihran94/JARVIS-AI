"""The workspace boundary of the coding agent.

WHAT IS COVERED
    * A path that leaves the project is refused, however it is written.
    * A link that points out of the project is refused.
    * A file the project keeps for itself is refused.
    * A file is written atomically, and an edit that does not match
      exactly changes nothing.
    * A patch is applied against the real text, and a patch that does not
      fit is refused instead of half-applied.
    * A search finds the text and says where it is.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

from core.coding_workspace import (
    CodingWorkspace, WorkspaceRefused, unified_diff,
)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    (root / 'src').mkdir(parents=True)
    (root / 'README.md').write_text('# The project\n', encoding='utf-8')
    (root / 'src' / 'main.py').write_text(
        'def add(a, b):\n    return a + b\n\n\ndef broken():\n    return 1\n', encoding='utf-8')
    (root / '.gitignore').write_text('secrets.json\n', encoding='utf-8')
    (root / 'secrets.json').write_text('{"key": "not-a-real-key"}\n', encoding='utf-8')
    return root


@pytest.fixture
def workspace(project):
    return CodingWorkspace(project)


# ── the boundary ───────────────────────────────────────────────────────────

def test_a_file_in_the_project_is_read(workspace):
    assert 'def add' in workspace.read_text('src/main.py')


def test_a_path_outside_the_project_is_refused(workspace, tmp_path):
    outside = tmp_path / 'outside.txt'
    outside.write_text('not yours', encoding='utf-8')
    with pytest.raises(WorkspaceRefused) as error:
        workspace.read_text(str(outside))
    assert 'outside the project' in str(error.value)


def test_a_run_of_dots_is_refused(workspace):
    with pytest.raises(WorkspaceRefused):
        workspace.read_text('../../etc/passwd')


def test_a_link_out_of_the_project_is_refused(workspace, tmp_path):
    target = tmp_path / 'secret.txt'
    target.write_text('secret', encoding='utf-8')
    link = workspace.root / 'link.txt'
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip('This system does not allow links.')
    with pytest.raises(WorkspaceRefused) as error:
        workspace.read_text('link.txt')
    assert 'link' in str(error.value).lower()


def test_a_file_the_project_keeps_is_refused(workspace):
    with pytest.raises(WorkspaceRefused) as error:
        workspace.read_text('secrets.json')
    assert 'protected' in str(error.value)


def test_a_protected_file_is_not_even_listed(workspace):
    assert 'secrets.json' not in workspace.list_files()


def test_a_secret_shaped_file_is_protected(workspace):
    (workspace.root / '.env').write_text('TOKEN=abc\n', encoding='utf-8')
    with pytest.raises(WorkspaceRefused):
        workspace.read_text('.env')


# ── listing and searching ──────────────────────────────────────────────────

def test_the_files_are_listed(workspace):
    files = workspace.list_files()
    assert 'README.md' in files
    assert 'src/main.py' in files
    assert '.git' not in ' '.join(files)


def test_a_folder_can_be_listed(workspace):
    assert workspace.list_files('src') == ['src/main.py']


def test_a_search_finds_the_text(workspace):
    found = workspace.search('def add')
    assert found
    assert found[0]['file'] == 'src/main.py'
    assert found[0]['line'] == 1


def test_a_search_that_finds_nothing_says_nothing(workspace):
    assert workspace.search('a string that is not there') == []


def test_a_search_that_is_not_a_pattern_is_refused(workspace):
    with pytest.raises(WorkspaceRefused):
        workspace.search('[unclosed')


# ── writing ────────────────────────────────────────────────────────────────

def test_a_file_is_written(workspace):
    name = workspace.write_text('src/new.py', 'print("hello")\n')
    assert name == 'src/new.py'
    assert (workspace.root / 'src' / 'new.py').read_text(encoding='utf-8') == 'print("hello")\n'


def test_a_file_that_is_already_there_is_not_replaced_by_create(workspace):
    with pytest.raises(WorkspaceRefused):
        workspace.create_file('README.md', 'other')


def test_an_exact_edit_is_applied(workspace):
    workspace.edit_file('src/main.py', 'return a + b', 'return a + b + 0')
    assert 'return a + b + 0' in (workspace.root / 'src' / 'main.py').read_text(encoding='utf-8')


def test_an_edit_that_is_not_there_changes_nothing(workspace):
    before = (workspace.root / 'src' / 'main.py').read_text(encoding='utf-8')
    with pytest.raises(WorkspaceRefused):
        workspace.edit_file('src/main.py', 'a line that is not there', 'x')
    assert (workspace.root / 'src' / 'main.py').read_text(encoding='utf-8') == before


def test_an_edit_that_matches_twice_is_refused(workspace):
    (workspace.root / 'src' / 'main.py').write_text('x\nx\n', encoding='utf-8')
    with pytest.raises(WorkspaceRefused) as error:
        workspace.edit_file('src/main.py', 'x', 'y')
    assert '2 times' in str(error.value)


def test_a_protected_file_is_not_written(workspace):
    with pytest.raises(WorkspaceRefused):
        workspace.write_text('secrets.json', '{"key": "other"}')


# ── patching ───────────────────────────────────────────────────────────────

def test_a_patch_is_applied(workspace):
    patch = (
        '--- a/src/main.py\n'
        '+++ b/src/main.py\n'
        '@@ -1,2 +1,2 @@\n'
        ' def add(a, b):\n'
        '-    return a + b\n'
        '+    return a - b\n'
    )
    result = workspace.apply_patch(patch)
    assert result.applied == 1
    assert 'return a - b' in (workspace.root / 'src' / 'main.py').read_text(encoding='utf-8')


def test_a_patch_that_does_not_fit_is_refused_and_nothing_changes(workspace):
    before = (workspace.root / 'src' / 'main.py').read_text(encoding='utf-8')
    patch = (
        '--- a/src/main.py\n'
        '+++ b/src/main.py\n'
        '@@ -1,2 +1,2 @@\n'
        ' def something else entirely(x):\n'
        '-    return 1\n'
        '+    return 2\n'
    )
    result = workspace.apply_patch(patch)
    assert result.applied == 0
    assert result.failed
    assert (workspace.root / 'src' / 'main.py').read_text(encoding='utf-8') == before


def test_a_patch_for_a_protected_file_is_refused(workspace):
    patch = ('--- a/secrets.json\n+++ b/secrets.json\n@@ -1 +1 @@\n-{"key": "not-a-real-key"}\n+{"key": "x"}\n')
    result = workspace.apply_patch(patch)
    assert result.applied == 0
    assert result.failed


def test_an_empty_patch_is_refused(workspace):
    with pytest.raises(WorkspaceRefused):
        workspace.apply_patch('   ')


def test_a_diff_can_be_made_for_the_owner_to_read():
    diff = unified_diff('a\nb\n', 'a\nc\n', 'file.txt')
    assert '-b' in diff
    assert '+c' in diff
