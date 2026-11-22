"""Natural addressing must retain approvals and literal user payloads."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from core.conversation import addressed_request
from desktop.voice_commands import parse_voice_command
from automation.desktop_tasks import parse_desktop_task
from developer_studio.commands import parse_command
from desktop.app import Window


@pytest.mark.parametrize('text,app', [
    ('Jarvis, CapCut open pannu', 'CapCut'),
    ('Hey Jarvis, please open Notepad', 'Notepad'),
    ('ஜார்விஸ், calculator திறந்து வை', 'Calculator'),
    ('J.A.R.V.I.S., launch CapCut', 'CapCut'),
])
def test_direct_requests_select_only_known_apps(text, app):
    assert parse_voice_command(text) == app


@pytest.mark.parametrize('text', [
    'please open notepad',
    'Jarvis, do not open Notepad',
    'Jarvis, how do I open Notepad?',
    'Jarvis, "open Notepad"',
    'Jarvis, open Notepad and delete my files',
    'Jarvis, open powershell',
    'Jarvis, if I say open Notepad what happens?',
])
def test_questions_negations_and_extra_actions_do_not_launch(text):
    assert parse_voice_command(text) is None
    assert parse_desktop_task(text) is None
    assert parse_command(text) is None


def test_addressing_does_not_modify_literal_task_payload():
    task = parse_desktop_task('Jarvis, please open Notepad and type: Hey Jarvis,\nPlease KEEP My தமிழ் Text!')
    assert task.text == 'Hey Jarvis,\nPlease KEEP My தமிழ் Text!'
    assert addressed_request('Jarvisville open Notepad') == 'Jarvisville open Notepad'


def test_conversational_commands_stay_local_and_preserve_approval(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    launches = []
    monkeypatch.setattr('desktop.app.launch_app', lambda name: launches.append(name))
    monkeypatch.setattr(win, 'get_key', lambda *_: pytest.fail('local request needs no provider'))
    try:
        win.prompt.setPlainText('Jarvis, ennoda projects kattu')
        win.send()
        assert 'No saved projects' in win.transcript.toPlainText()
        win.prompt.setPlainText('Hey Jarvis, please open Notepad')
        win.send()
        assert win.chat_launch is not None
        assert launches == []
        win.finish_chat_launch(False)
        assert launches == []
        win.prompt.setPlainText('Jarvis, open Notepad')
        win.send()
        win.stop()
        assert launches == []
        assert win.chat_launch is None
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_chat_keeps_original_user_words_and_honest_personality(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    calls = []
    monkeypatch.setattr(win, 'get_key', lambda *_: 'test-only')
    monkeypatch.setattr(win, 'start_worker', lambda *args, **kwargs: calls.append(args))
    try:
        text = 'Jarvis, எனக்கு ஒரு நல்ல நண்பன் மாதிரி பேசு'
        win.prompt.setPlainText(text)
        win.send()
        assert len(calls) == 1
        messages = calls[0][3]
        assert messages[-1]['content'] == text
        assert 'friendly, practical personal AI assistant' in messages[0]['content']
        assert 'Never claim' in messages[0]['content']
        assert win.chat_launch is None
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_addressed_video_brief_reaches_existing_workflow_unchanged(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    briefs = []
    monkeypatch.setattr(win, 'generate_video_plan', lambda **kwargs: briefs.append(kwargs['chat_brief']))
    try:
        win.prompt.setPlainText('Jarvis, /video தமிழ் Story: KEEP This Case')
        win.send()
        assert briefs == ['தமிழ் Story: KEEP This Case']
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_explicit_analysis_cannot_schedule_coding(tmp_path, monkeypatch):
    from developer_studio.projects import SavedProject
    from providers.profiles import model_for

    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    calls = []
    monkeypatch.setattr(win, 'get_key', lambda *_: 'test-only')
    monkeypatch.setattr(win, 'start_worker', lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr('desktop.app.load_projects', lambda _: [
        SavedProject('project-a', str(tmp_path), 'VS Code', 'pytest'),
    ])
    monkeypatch.setattr(win, 'start_coding_task', lambda *_: pytest.fail('Analysis scheduled a change'))
    try:
        win.prompt.setPlainText('/analyze project-a fix login and run tests')
        win.send()
        provider, model, _, messages, kind = calls[0]
        assert (provider, model, kind) == ('Gemini', model_for('Gemini', 'deep'), 'chat')
        assert messages[-1]['content'] == 'project-a fix login and run tests'
        assert win.stored_profile('Gemini') == 'fast'
    finally:
        win.close()
        app.processEvents()



@pytest.mark.parametrize('text', [
    'Déboguer les erreurs du projet',
    'இந்தப் பிழையைக் கண்டுபிடி',
    'padi padiya explain pannu',
])
def test_auto_effort_recognizes_multilingual_analysis(text):
    from providers.task_brain import effort_for

    assert effort_for(text) == 'deep'
    assert effort_for(text, 'Fast') == 'fast'
