"""Looking at a project before anything is changed.

WHAT IS COVERED
    * The shape of a project is reported: the files at the top, how many
      files of each kind there are, and how many were looked at.
    * A Python file that does not compile is found, with the line.
    * A JSON file that is not JSON is found, with the line.
    * A file that holds a secret, and a file the project's own
      `.gitignore` keeps out, are not looked at.
    * The project is bounded: only so many files, only so deep.
"""
import pytest
from PySide6.QtWidgets import QApplication

from developer_studio.inspection import (
    MAX_DEPTH, MAX_FILES, inspect_project,
)
from developer_studio.projects import SavedProject, load_projects


def make_project(tmp_path):
    (tmp_path / 'app.py').write_text('print("hello")\n', encoding='utf-8')
    (tmp_path / 'data.json').write_text('{"a": 1}\n', encoding='utf-8')
    package = tmp_path / 'pkg'
    package.mkdir()
    (package / 'module.py').write_text('VALUE = 1\n', encoding='utf-8')
    return tmp_path


def test_the_shape_of_a_project_is_reported(tmp_path):
    project = make_project(tmp_path)
    result = inspect_project(project)
    assert result.files_inspected == 3
    assert result.kinds['py'] == 2
    assert result.kinds['json'] == 1
    assert 'app.py' in result.top_level
    assert 'pkg' in result.top_level
    assert '3 file(s) looked at' in result.summary()


def test_a_python_file_that_does_not_compile_is_found(tmp_path):
    (tmp_path / 'broken.py').write_text('def oops(:\n    pass\n', encoding='utf-8')
    result = inspect_project(tmp_path)
    assert result.problem_count == 1
    problem = result.problems[0]
    assert problem.path == 'broken.py'
    assert problem.kind == 'python syntax'
    assert problem.line >= 1
    assert 'broken.py' in result.summary()


def test_a_json_file_that_is_not_json_is_found(tmp_path):
    (tmp_path / 'broken.json').write_text('{"a": 1,,}\n', encoding='utf-8')
    result = inspect_project(tmp_path)
    assert result.problem_count == 1
    assert result.problems[0].path == 'broken.json'
    assert result.problems[0].kind == 'invalid JSON'


def test_a_good_project_reports_no_problems(tmp_path):
    make_project(tmp_path)
    result = inspect_project(tmp_path)
    assert result.problems == []
    assert 'No problem that can be found without running the code' in result.summary()


def test_a_file_of_secrets_is_not_looked_at(tmp_path):
    (tmp_path / '.env').write_text('SECRET=1\n', encoding='utf-8')
    (tmp_path / 'ok.py').write_text('X = 1\n', encoding='utf-8')
    result = inspect_project(tmp_path)
    assert result.files_inspected == 1
    assert result.files_skipped == 1
    assert '.env' not in result.top_level


def test_a_file_the_project_keeps_out_is_not_looked_at(tmp_path):
    (tmp_path / '.gitignore').write_text('local/\n*.key\n', encoding='utf-8')
    (tmp_path / 'ok.py').write_text('X = 1\n', encoding='utf-8')
    local = tmp_path / 'local'
    local.mkdir()
    (local / 'settings.py').write_text('SECRET = 1\n', encoding='utf-8')
    (tmp_path / 'private.key').write_text('-----BEGIN PRIVATE KEY-----\n')
    result = inspect_project(tmp_path)
    looked = [name for name in result.top_level]
    assert 'ok.py' in looked
    # The key is off limits by its name, and the folder the project keeps
    # out is not walked into, so nothing inside it is read either.
    assert 'private.key' not in looked
    # ok.py and the .gitignore itself are looked at; the key and the file
    # inside the folder the project keeps out are not.
    assert result.files_inspected == 2
    assert result.files_skipped == 2
    assert not any(problem.path.startswith('local/') for problem in result.problems)


def test_a_folder_that_is_not_there_says_so(tmp_path):
    result = inspect_project(tmp_path / 'missing')
    assert result.files_inspected == 0
    assert 'not there any more' in result.summary()


def test_the_look_is_bounded(tmp_path):
    for index in range(MAX_FILES + 20):
        (tmp_path / f'file{index}.py').write_text('X = 1\n', encoding='utf-8')
    result = inspect_project(tmp_path)
    assert result.files_inspected <= MAX_FILES
    assert result.truncated is True
    assert 'larger than the limit' in result.summary()


def test_a_deep_folder_is_not_looked_at(tmp_path):
    deep = tmp_path
    for _ in range(MAX_DEPTH + 3):
        deep = deep / 'level'
    deep.mkdir(parents=True)
    (deep / 'deep.py').write_text('X = 1\n', encoding='utf-8')
    result = inspect_project(tmp_path)
    assert 'deep.py' not in ' '.join(result.top_level)


def test_the_problems_are_given_to_a_coding_model_on_their_own(tmp_path):
    (tmp_path / 'broken.py').write_text('def oops(:\n', encoding='utf-8')
    result = inspect_project(tmp_path)
    text = result.problems_text()
    assert 'broken.py' in text
    assert 'python syntax' in text


def test_no_summary_ever_invents_a_percentage(tmp_path):
    (tmp_path / 'broken.py').write_text('def oops(:\n', encoding='utf-8')
    result = inspect_project(tmp_path)
    assert '%' not in result.summary()
    assert 'percent' not in result.summary().casefold()


# ── in the developer flow ───────────────────────────────────────────────────

def test_the_prompt_carries_what_was_already_found(tmp_path):
    """The model is told what was found, so it works on the real problem."""
    from developer_studio.codex_task import build_prompt
    from developer_studio.projects import SavedProject

    project = SavedProject(name='project-a', path=str(tmp_path), editor='VS Code')
    prompt = build_prompt(project, 'fix the login', None,
                          'broken.py: python syntax: invalid syntax')
    assert 'broken.py' in prompt
    assert 'already looked at the project' in prompt
    # The owner's own words are still the whole request.
    assert 'fix the login' in prompt


def test_the_task_carries_the_counts_into_its_outcome(tmp_path):
    from developer_studio.codex_task import CodexTask
    from developer_studio.projects import SavedProject

    project = SavedProject(name='project-a', path=str(tmp_path), editor='VS Code')
    task = CodexTask(project, 'fix the login', files_inspected=42, problems_found=3)
    assert task.outcome.files_inspected == 42
    assert task.outcome.problems_found == 3
    assert task.outcome.as_dict()['files_inspected'] == 42


def test_the_card_says_what_was_found_before_anything_changed(tmp_path, monkeypatch):
    """The owner sees the facts before the model is asked to do anything."""
    import desktop.app as desktop
    from core.store import Store
    from developer_studio.projects import SavedProject, save_projects

    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / 'history.sqlite3')
    folder = tmp_path / 'project-a'
    folder.mkdir()
    (folder / 'app.py').write_text('print("ok")\n', encoding='utf-8')
    (folder / 'broken.py').write_text('def oops(:\n', encoding='utf-8')
    save_projects(store, [SavedProject(name='project-a', path=str(folder),
                                       editor='VS Code')])
    window = desktop.Window(tmp_path)
    try:
        projects = load_projects(window.store)
        request = desktop.parse_coding_request(
            'JARVIS, project-a open panni fix pannu', projects)
        assert request is not None
        window.start_coding_task(request, 'fix the login')
        text = window.chat_task_text.text()
        assert 'file(s) looked at' in text
        assert 'problem(s) found' in text
        assert 'broken.py' in text
        assert '%' not in text
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
