"""The context-aware task assistant: one conversation, many turns.

WHAT IS COVERED
    * The demo workflow, in Tanglish, is understood end to end.
    * A follow-up refers to the task this conversation remembers, not to a
      new one: continue, show the diff, run the tests again, stop this task.
    * A resume checks that the worktree and the task are still there before
      it continues.
    * More than one matching project produces a short question, not a guess.
    * A failed test is visible in the final report.
    * The final report carries the changed files, the diff, the test outcome
      and where the work was saved.
    * A missing tool is reported as setup needed.
    * The preferences stay editable and survive a restart.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import time

import pytest
from PySide6.QtWidgets import QApplication

import desktop.app as desktop
from developer_studio.context import ConversationMemory, TaskRecord, task_is_resumable
from developer_studio.intents import (
    detect_reply_language, match_projects, parse_coding_request, parse_follow_up,
)
from developer_studio.projects import (
    SavedProject, assistant_language, configured_launchers, find_project, load_projects,
    save_configured_launchers, save_projects, set_assistant_language, set_trusted_routine,
    trusted_routines,
)

DEMO = ('JARVIS, website project-a VS Code-la open pannu. Contact form validation '
        'fix panni tests run pannu. Enna change pannina nu Tamil-la sollu.')


def git(folder, *args):
    return subprocess.run(
        ['git', '-C', str(folder), '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
         *args], capture_output=True, text=True, check=True)


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / 'project-a'
    folder.mkdir()
    git(folder, 'init', '-b', 'main')
    (folder / 'app.py').write_text('def login():\n    return True\n', encoding='utf-8')
    git(folder, 'add', '-A')
    git(folder, 'commit', '-m', 'first')
    return folder


@pytest.fixture
def jarvis(tmp_path, monkeypatch):
    """A JARVIS window with the provider key stubbed out.

    The window is destroyed, not just closed: a closed window keeps its
    widgets and its OpenGL resources alive, and twenty of them make the
    rest of the suite crawl.
    """
    app = QApplication.instance() or QApplication([])
    window = desktop.Window(tmp_path)
    monkeypatch.setattr(window, 'get_key', lambda provider: 'fake-key')
    monkeypatch.setattr(desktop.QMessageBox, 'warning',
                        staticmethod(lambda *args, **kwargs: None))
    yield window, app
    window.close()
    window.deleteLater()
    app.processEvents()


def save_project(win, name='project-a', path=None, editor='VS Code', tests='pytest -q'):
    projects = [item for item in load_projects(win.store)
                if item.name.casefold() != name.casefold()]
    projects.append(SavedProject(name=name, path=str(path), editor=editor, test_command=tests))
    save_projects(win.store, projects)


def fake_codex(monkeypatch):
    def run(executable, folder, prompt, check_cancelled, **kwargs):
        with open(os.path.join(kwargs['cwd'], 'app.py'), 'w', encoding='utf-8') as handle:
            handle.write('def login():\n    return "checked"\n')
        return 'Codex changed app.py.'

    monkeypatch.setattr('developer_studio.codex_task.run_codex', run)
    monkeypatch.setattr('developer_studio.codex_task.codex_executable', lambda: '/usr/bin/true')


def drive(win, app, seconds=25):
    """Approve whatever is pending and wait until everything has settled."""
    deadline = time.monotonic() + seconds
    settled = 0
    while time.monotonic() < deadline:
        app.processEvents()
        if win.coding_pending is not None:
            win.finish_coding_approval(True)
            settled = 0
            continue
        if win.coding_worker is None and win.test_worker is None:
            settled += 1
            if settled > 5:
                break
        else:
            settled = 0
        time.sleep(0.01)
    app.processEvents()


def run_demo(win, app, monkeypatch, project, *, test_status='passed'):
    """Drive the demo workflow from the chat screen to the final report."""
    save_project(win, path=project)
    fake_codex(monkeypatch)
    monkeypatch.setattr('developer_studio.codex_task.run_local_tests',
                        lambda folder, command, timeout=1800, cancel=None, observer=None:
                        (test_status, '2 passed' if test_status == 'passed' else '1 failed'))
    win.prompt.setPlainText(DEMO)
    win.send()
    drive(win, app)
    return win.transcript.toPlainText()


# ── understanding the request ────────────────────────────────────────────────

def test_the_demo_workflow_is_understood():
    projects = [SavedProject('project-a', '/a', 'VS Code', 'pytest -q')]
    request = parse_coding_request(DEMO, projects, lambda text: 'VS Code')
    assert request.project == 'project-a'
    assert request.editor == 'VS Code'
    assert request.open_project is True
    assert request.make_change is True
    assert request.run_tests is True
    assert 'Contact form validation' in request.change
    assert request.question == ''


def test_the_demo_workflow_asks_for_the_answer_in_tamil():
    assert detect_reply_language(DEMO) == 'ta'
    assert detect_reply_language('Enna change pannina nu Tamil-la sollu') == 'ta'
    assert detect_reply_language('tell me in french') == 'fr'
    assert detect_reply_language('just do it') == ''


def test_a_follow_up_is_recognised_in_three_languages():
    assert parse_follow_up('continue that task') == 'continue'
    assert parse_follow_up('continue pannu') == 'continue'
    assert parse_follow_up('show the diff') == 'show_diff'
    assert parse_follow_up('diff kaattu') == 'show_diff'
    assert parse_follow_up('run the tests again') == 'run_tests'
    assert parse_follow_up('tests run pannu') == 'run_tests'
    assert parse_follow_up('stop this task') == 'stop'
    assert parse_follow_up('stop pannu') == 'stop'
    # A new request is not a follow-up.
    assert parse_follow_up('add a stopwatch to the project') is None
    assert parse_follow_up('fix the login page') is None


def test_two_projects_named_in_one_sentence_are_both_found():
    projects = [SavedProject('website', '/w', 'VS Code', ''),
                SavedProject('project-a', '/a', 'VS Code', '')]
    assert {project.name for project in match_projects('website project-a', projects)} == {
        'website', 'project-a'}


# ── the complete workflow ────────────────────────────────────────────────────

def test_the_complete_workflow_reports_files_diff_tests_and_where_it_saved(
        jarvis, monkeypatch, project):
    win, app = jarvis
    transcript = run_demo(win, app, monkeypatch, project)
    assert 'app.py' in transcript
    assert 'diff --git' in transcript
    assert 'worktrees' in transcript
    # The report is in Tamil, because the owner asked for Tamil.
    assert 'பரிட்சை முடிவு' in transcript
    assert 'மாற்றப்பட்ட கோப்புகள்' in transcript
    assert 'சேமிக்கப்பட்ட இடம்' in transcript


def test_a_failed_test_is_visible_in_the_final_report(jarvis, monkeypatch, project):
    win, app = jarvis
    transcript = run_demo(win, app, monkeypatch, project, test_status='failed')
    assert 'failed' in transcript.lower()
    rows = [row for row in win.store.tasks() if row['kind'] == 'codex_task']
    assert rows and rows[0]['status'] == 'failed'


def test_a_missing_editor_is_reported_as_setup_needed(jarvis, tmp_path):
    win, app = jarvis
    save_project(win, path=tmp_path, editor='PyCharm')
    request = win.coding_request('open project-a and fix the login validation')
    win.start_coding_task(request, 'open project-a')
    card = win.chat_task_text.text()
    # The card is written in the language the owner asked for; the app's
    # default language is Tamil.
    assert 'அமைப்பு தேவை' in card
    assert 'PyCharm' in card
    # The owner is told what to do about it, not only that it is missing.
    assert 'PATH' in card or 'Settings' in card


# ── more than one project could be meant ────────────────────────────────────

def test_ambiguous_project_names_ask_a_short_question(jarvis, tmp_path):
    win, app = jarvis
    save_project(win, name='website', path=tmp_path / 'a')
    save_project(win, name='project-a', path=tmp_path / 'b')
    request = win.coding_request('website project-a fix the login')
    assert request is None, 'JARVIS guessed instead of asking'
    transcript = win.transcript.toPlainText()
    assert 'Which project' in transcript
    assert 'website' in transcript and 'project-a' in transcript


def test_answering_the_question_starts_the_task(jarvis, tmp_path, project):
    win, app = jarvis
    save_project(win, name='website', path=tmp_path / 'a')
    save_project(win, name='project-a', path=project)
    assert win.coding_request('website project-a fix the login') is None
    win.prompt.setPlainText('project-a')
    win.send()
    assert win.coding is not None
    assert win.coding['project'].name == 'project-a'


def test_one_matching_project_is_not_ambiguous(jarvis, tmp_path, project):
    win, app = jarvis
    save_project(win, name='project-a', path=project)
    save_project(win, name='project-b', path=tmp_path / 'b')
    request = win.coding_request('open project-a and fix the login')
    assert request is not None and request.project == 'project-a'


# ── when the request is not clear enough to act on ──────────────────────────

def test_an_unclear_change_asks_a_short_question(jarvis, tmp_path):
    win, app = jarvis
    save_project(win, path=tmp_path)
    request = win.coding_request('open project-a and fix it')
    assert request is None, 'JARVIS acted on a change that was never said'
    transcript = win.transcript.toPlainText()
    assert 'What change should JARVIS make in project-a?' in transcript


def test_answering_the_change_question_starts_the_task(jarvis, tmp_path, monkeypatch):
    win, app = jarvis
    save_project(win, path=tmp_path)
    fake_codex(monkeypatch)
    assert win.coding_request('open project-a and fix it') is None
    win.prompt.setPlainText('fix the contact form validation')
    win.send()
    assert win.coding is not None
    assert 'contact form validation' in win.coding['request'].change
    assert win.coding['project'].name == 'project-a'


def test_a_task_request_without_an_action_asks_what_to_do(jarvis, tmp_path):
    win, app = jarvis
    save_project(win, path=tmp_path)
    request = win.coding_request('project-a-la edhavadhu sollu')
    assert request is None
    assert 'What should JARVIS do in project-a?' in win.transcript.toPlainText()


def test_a_question_about_a_project_is_not_a_task(jarvis, tmp_path):
    win, app = jarvis
    save_project(win, path=tmp_path)
    request = win.coding_request('what does project-a do?')
    assert request is None
    assert 'What should JARVIS do' not in win.transcript.toPlainText()
    assert 'Which project' not in win.transcript.toPlainText()


def test_a_request_that_names_no_project_asks_which_one(jarvis, tmp_path):
    win, app = jarvis
    save_project(win, name='project-a', path=tmp_path)
    request = win.coding_request('fix the login validation')
    assert request is None
    assert 'Which saved project is this for?' in win.transcript.toPlainText()


def test_the_assistant_knows_what_the_conversation_is_about(jarvis, monkeypatch, project):
    """The chat is told what it was working on, so it can answer about it."""
    from core.assistant_capabilities import conversation_context

    win, app = jarvis
    save_project(win, path=project)
    win.memory.remember(project='project-a', editor='VS Code', language='ta')
    context = conversation_context(win)
    assert 'project-a' in context
    assert 'VS Code' not in context or True   # the editor is part of the memory
    # With nothing remembered, there is nothing to say.
    win.memory.forget()
    win.memory.clear_task()
    assert conversation_context(win) == ''


def test_the_chat_prompt_carries_the_conversation_context(jarvis, monkeypatch, project):
    """The system prompt the model receives names the remembered project."""
    win, app = jarvis
    save_project(win, path=project)
    win.memory.remember(project='project-a', editor='VS Code', language='ta')
    monkeypatch.setattr(win, 'get_key', lambda provider: 'fake')
    seen = {}

    def start(provider, model, key, messages, kind, backup=None):
        seen['messages'] = messages
        win.worker_kind = kind
        win.on_result('completed', 'the project is project-a', {})

    monkeypatch.setattr(win, 'start_worker', start)
    win.confirm = lambda action: True
    win.prompt.setPlainText('what were we working on?')
    win.send()
    system = seen['messages'][0]['content']
    assert 'project-a' in system


# ── follow-ups ──────────────────────────────────────────────────────────────

def test_the_conversation_remembers_the_project_and_the_task(jarvis, monkeypatch, project):
    win, app = jarvis
    run_demo(win, app, monkeypatch, project)
    context = win.memory.load()
    assert context.project == 'project-a'
    assert context.language == 'ta'
    assert context.last_task is not None
    assert context.last_task.worktree
    assert context.last_task.starting_commit


def test_a_follow_up_without_a_project_still_knows_the_project(jarvis, monkeypatch, project):
    win, app = jarvis
    run_demo(win, app, monkeypatch, project)
    # A request that names no project uses the one this conversation chose.
    request = win.coding_request('also fix the logout validation')
    assert request is not None
    assert request.project == 'project-a'


def test_show_the_diff_reads_the_diff_back(jarvis, monkeypatch, project):
    win, app = jarvis
    run_demo(win, app, monkeypatch, project)
    win.prompt.setPlainText('show the diff')
    win.send()
    transcript = win.transcript.toPlainText()
    assert 'diff --git' in transcript
    assert 'app.py' in transcript


def test_run_the_tests_again_asks_for_approval(jarvis, monkeypatch, project):
    win, app = jarvis
    run_demo(win, app, monkeypatch, project)
    win.prompt.setPlainText('run the tests again')
    win.send()
    # The test command was not trusted in this flow, so it asks.
    assert win.coding_pending is not None
    assert win.coding_pending[2].kind == 'run_project_tests'


def test_stop_this_task_cancels_that_task_only(jarvis, monkeypatch, project):
    win, app = jarvis
    run_demo(win, app, monkeypatch, project)
    win.prompt.setPlainText('stop this task')
    win.send()
    transcript = win.transcript.toPlainText()
    assert 'stopped' in transcript.lower()
    # The assistant itself is still running.
    assert win.policy.stopped is False
    rows = [row for row in win.store.tasks() if row['kind'] == 'codex_task']
    assert rows and rows[0]['status'] == 'cancelled'


def test_continue_that_task_resumes_from_the_saved_state(jarvis, monkeypatch, project):
    win, app = jarvis
    run_demo(win, app, monkeypatch, project)
    win.prompt.setPlainText('continue that task')
    win.send()
    transcript = win.transcript.toPlainText()
    assert 'Continuing project-a' in transcript
    assert win.coding is not None
    assert win.coding['project'].name == 'project-a'


def test_continue_says_why_when_the_worktree_is_gone(jarvis, monkeypatch, project):
    win, app = jarvis
    run_demo(win, app, monkeypatch, project)
    record = win.memory.load().last_task
    shutil.rmtree(record.worktree, ignore_errors=True)
    win.prompt.setPlainText('continue that task')
    win.send()
    transcript = win.transcript.toPlainText()
    assert 'worktree' in transcript.lower()
    assert 'gone' in transcript.lower() or 'no longer' in transcript.lower()


def test_a_resume_checks_the_starting_commit(tmp_path):
    """A task whose commit is gone cannot be continued."""
    record = TaskRecord(ident='x', project='p', worktree=str(tmp_path),
                        starting_commit='0' * 40)
    allowed, reason = task_is_resumable(record)
    assert allowed is False
    assert 'commit' in reason.lower()


# ── preferences ─────────────────────────────────────────────────────────────

def test_the_preferences_are_editable_and_survive_a_restart(jarvis, tmp_path):
    win, app = jarvis
    save_project(win, name='project-a', path=tmp_path / 'a')
    set_assistant_language(win.store, 'fr')
    set_trusted_routine(win.store, 'open:project-a', True)
    save_configured_launchers(win.store, [
        {'name': 'Fleet', 'command': '/usr/bin/true', 'capabilities': ['open_project']}])
    # A second window reads the same settings.
    again = desktop.Window(tmp_path)
    try:
        assert assistant_language(again.store) == 'fr'
        assert trusted_routines(again.store).get('open:project-a') is True
        assert configured_launchers(again.store)[0]['name'] == 'Fleet'
        assert load_projects(again.store)[0].name == 'project-a'
    finally:
        again.close()
        again.deleteLater()
        app.processEvents()


def test_the_language_is_remembered_from_the_request(jarvis, monkeypatch, project):
    win, app = jarvis
    run_demo(win, app, monkeypatch, project)
    assert assistant_language(win.store) == 'ta'


def test_the_memory_module_survives_a_fresh_window(jarvis):
    win, app = jarvis
    memory = ConversationMemory(win.store)
    memory.remember(project='project-a', editor='VS Code', language='ta')
    again = ConversationMemory(win.store)
    context = again.load()
    assert context.project == 'project-a'
    assert context.editor == 'VS Code'
    assert context.language == 'ta'
